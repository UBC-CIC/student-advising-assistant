import {
  Stack,
  StackProps,
  Duration,
  RemovalPolicy,
  CfnParameter,
  CfnCondition,
  Fn,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as iam from "aws-cdk-lib/aws-iam";
import { VpcStack } from "./vpc-stack";
import * as ecs from "aws-cdk-lib/aws-ecs";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import * as path from "path";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as triggers from "aws-cdk-lib/triggers";
import { DatabaseStack } from "./database-stack";
import * as ecsPatterns from "aws-cdk-lib/aws-ecs-patterns";
import * as events from "aws-cdk-lib/aws-events";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3n from "aws-cdk-lib/aws-s3-notifications";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import {readFileSync} from 'fs';
import config from '../config.json';

export class InferenceStack extends Stack {
  public readonly psycopg2_layer: lambda.LayerVersion;
  public readonly lambda_rds_role: iam.Role;
  public readonly S3_SSM_PARAM_NAME: string;
  public readonly ENDPOINT_TYPE: string;
  public readonly ENDPOINT_NAME: string;

  constructor(
    scope: Construct,
    id: string,
    vpcStack: VpcStack,
    databaseStack: DatabaseStack,
    props?: StackProps
  ) {
    super(scope, id, props);

    this.S3_SSM_PARAM_NAME = "/student-advising/documents/S3_BUCKET_NAME"
    const vpc = vpcStack.vpc;

    // Bucket for files related to inference
    const inferenceBucket = new s3.Bucket(this, "student-advising-s3bucket", {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    // Create the SSM parameter with the string value representing the S3 bucket name
    new ssm.StringParameter(this, "S3BucketNameParameter", {
      parameterName: this.S3_SSM_PARAM_NAME,
      stringValue: inferenceBucket.bucketName, // Replace 'your-s3-bucket-name' with the actual S3 bucket name
    });

    const clusterSg = new ec2.SecurityGroup(this, "cluster-sg", {
      vpc: vpc,
      allowAllOutbound: true,
    });

    // this role will be used for both task role and task execution role
    const ecsTaskRole = new iam.Role(this, "ecs-task-role", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      description: "Role for ecs task",
    });
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AmazonECSTaskExecutionRolePolicy"
      )
    );
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonS3FullAccess")
    );
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("SecretsManagerReadWrite")
    );
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMReadOnlyAccess")
    );
    ecsTaskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["logs:CreateLogGroup"],
        resources: ["*"],
      })
    );

    const fargateCluster = new ecs.Cluster(this, "datapipeline-cluster", {
      vpc: vpc,
      enableFargateCapacityProviders: true,
    });

    const ecsTaskDef = new ecs.FargateTaskDefinition(
      this,
      "datapipeline-taskdef",
      {
        cpu: 16384,
        memoryLimitMiB: 32768,
        taskRole: ecsTaskRole,
        executionRole: ecsTaskRole,
        runtimePlatform: {
          operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
          cpuArchitecture: ecs.CpuArchitecture.X86_64
        },
        family: "scraping-and-embedding-16cpu-32gb",
      }
    );
    const scraping_container = ecsTaskDef.addContainer(
      "datapipeline-scraping",
      {
        containerName: "scraping-container",
        image: ecs.ContainerImage.fromAsset(
          path.join(__dirname, "..", "..", ".."),
          {
            file: path.join("scraping.Dockerfile"),
          }
        ),
        logging: ecs.LogDrivers.awsLogs({
          streamPrefix: "student-advising",
          logRetention: RetentionDays.ONE_YEAR,
        }),
        environment: {
          AWS_DEFAULT_REGION: this.region
        },
        essential: false,
        // gpuCount: 1,
      }
    );
    const embedding_container = ecsTaskDef.addContainer(
      "datapipeline-document-embeddings",
      {
        containerName: "embedding-container",
        image: ecs.ContainerImage.fromAsset(
          path.join(__dirname, "..", "..", ".."),
          {
            file: path.join("embedding.Dockerfile"),
          }
        ),
        logging: ecs.LogDrivers.awsLogs({
          streamPrefix: "student-advising",
          logRetention: RetentionDays.ONE_YEAR,
        }),
        essential: true,
        cpu: 14336, // 14 vCPU
        environment: {
          // ECS_ENABLE_GPU_SUPPORT: "true",
          AWS_DEFAULT_REGION: this.region
        }
      }
    );
    // only start the embedding container when the scraping container successfully exit without error
    embedding_container.addContainerDependencies({
      container: scraping_container,
      condition: ecs.ContainerDependencyCondition.SUCCESS,
    });

    const startECSTaskLambda = new lambda.Function(
      this,
      "student-advising-start-ecs-task",
      {
        functionName: "student-advising-start-ecs-task",
        runtime: lambda.Runtime.PYTHON_3_9,
        handler: "start_ecs_task.lambda_handler",
        timeout: Duration.seconds(300),
        memorySize: 512,
        environment: {
          ECS_CLUSTER_NAME: fargateCluster.clusterName,
          ECS_TASK_ARN: ecsTaskDef.taskDefinitionArn,
          PRIV_SUBNET: vpcStack.vpc.isolatedSubnets[0].subnetId,
          SGR: clusterSg.securityGroupId,
        },
        vpc: vpcStack.vpc,
        code: lambda.Code.fromAsset("./lambda/start_ecs_task"),
      }
    );
    startECSTaskLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["iam:PassRole", "ecs:RunTask"],
        resources: [
          ecsTaskRole.roleArn,
          `arn:aws:ecs:*:${this.account}:task-definition/*:*`,
        ],
      })
    );
    // S3ReadOnlyAccess
    startECSTaskLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "s3:Get*",
          "s3:List*",
          "s3-object-lambda:Get*",
          "s3-object-lambda:List*",
        ],
        resources: ["*"],
      })
    );

    inferenceBucket.addObjectCreatedNotification(
      new s3n.LambdaDestination(startECSTaskLambda),
      {
        prefix: "document_scraping/dump_config.json5",
      }
    );

    // Upload only the dump_config.json5 file instead of entire document_scraping directory
    const s3Deploy1 = new s3deploy.BucketDeployment(
      this,
      "upload-dump-config",
      {
        sources: [
          s3deploy.Source.asset(
            path.join(__dirname, "..", "..", "..", "document_scraping"),
            { exclude: ["**", ".*", "!dump_config.json5"] }
          ),
        ],
        destinationBucket: inferenceBucket,
        destinationKeyPrefix: "document_scraping",
      }
    );
    s3Deploy1.node.addDependency(startECSTaskLambda);

    // Create a scheduled fargate task that runs at 8:00 UTC on the first of every month
    const scheduledFargateTask = new ecsPatterns.ScheduledFargateTask(
      this,
      "ScheduledFargateTask",
      {
        cluster: fargateCluster,
        scheduledFargateTaskDefinitionOptions: {
          taskDefinition: ecsTaskDef,
        },
        securityGroups: [clusterSg],
        // CRON: At 01:00 AM, on the first Sunday of the month, only in September, January, and May
        schedule: events.Schedule.expression("cron(0 0 ? SEP,JAN,MAY SUN#1 *)"),
        subnetSelection: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      }
    );

    const lambdaRole = new iam.Role(this, "lambda-vpc-role", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "Role for all Lambda function inside vpc",
    });
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          //Secrets Manager
          "secretsmanager:GetSecretValue",
        ],
        resources: [
          `arn:aws:secretsmanager:${this.region}:${this.account}:secret:student-advising/credentials/*`,
        ],
      })
    );
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          // CloudWatch Logs
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: ["arn:aws:logs:*:*:*"],
      })
    );
    lambdaRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "ec2:CreateNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
        ],
        resources: ["*"],
      })
    );
    lambdaRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMReadOnlyAccess")
    );
    lambdaRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonS3FullAccess")
    );
    this.lambda_rds_role = lambdaRole;

    // The layer containing the psycopg2 library
    const psycopg2 = new lambda.LayerVersion(this, "psycopg2", {
      code: lambda.Code.fromAsset("layers/psycopg2.zip"),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
      description: "psycopg2 library for connecting to the PostgreSQL database",
    });
    this.psycopg2_layer = psycopg2;

    // Trigger function to set up database
    const triggerLambda = new triggers.TriggerFunction(
      this,
      "student-advising-triggerLambda",
      {
        functionName: "student-advising-setup-database",
        runtime: lambda.Runtime.PYTHON_3_9,
        handler: "setup_database.lambda_handler",
        timeout: Duration.seconds(300),
        memorySize: 512,
        environment: {
          DB_SECRET_NAME: databaseStack.secretPath,
        },
        vpc: vpcStack.vpc,
        code: lambda.Code.fromAsset("./lambda/trigger_lambda"),
        layers: [psycopg2],
        role: lambdaRole,
      }
    );

    // LLM configuration
    const HUGGINGFACE_MODEL_ID = "arya/vicuna-7b-v1.5-hf";
    const MODEL_NAME = "vicuna";

    if (config.llm_mode == "sagemaker") {
      this.ENDPOINT_NAME = MODEL_NAME + "-inference";
      this.ENDPOINT_TYPE = "sagemaker";
      const INSTANCE_TYPE = "ml.g5.xlarge";
      const NUM_GPUS = "1";

      // Role for Sagemaker
      // this role will be used for both task role and task execution role
      const smRole = new iam.Role(this, "sagemaker-role", {
        assumedBy: new iam.ServicePrincipal("sagemaker.amazonaws.com"),
        description: "Role for Sagemaker to create inference endpoint",
      });
      smRole.addManagedPolicy(
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSagemakerFullAccess")
      );

      const createSMEndpointLambda = new triggers.TriggerFunction(
        this,
        "student-advising-create-sm-endpoint",
        {
          functionName: "student-advising-create-sagemaker-endpoint",
          runtime: lambda.Runtime.PYTHON_3_9,
          handler: "create_sagemaker_endpoint.lambda_handler",
          timeout: Duration.seconds(300),
          memorySize: 512,
          environment: {
            SM_ENDPOINT_NAME: this.ENDPOINT_NAME,
            SM_REGION: this.region,
            SM_ROLE_ARN: smRole.roleArn,
            HF_MODEL_ID: HUGGINGFACE_MODEL_ID,
            MODEL_NAME: MODEL_NAME,
            INSTANCE_TYPE: INSTANCE_TYPE,
            NUM_GPUS: NUM_GPUS,
          },
          vpc: vpcStack.vpc,
          vpcSubnets: {
            subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          },
          code: lambda.Code.fromAsset("./lambda/create_sagemaker_endpoint"),
        }
      );
      createSMEndpointLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            // CloudWatch Logs
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
          ],
          resources: ["arn:aws:logs:*:*:*"],
        })
      );
      createSMEndpointLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "sagemaker:AddTags",
            "sagemaker:CreateModel",
            "sagemaker:CreateEndpointConfig",
            "sagemaker:CreateEndpoint",
            "iam:PassRole"
          ],
          resources: ["*"],
        })
      );
    } else if (config.llm_mode == "ec2") {
      this.ENDPOINT_TYPE = "huggingface_tgi";

      const vpc = vpcStack.vpc

      // Security group for the EC2 instance
      const ec2SG = new ec2.SecurityGroup(this, 'student-advising-ec2-tgi-sg', {
        vpc,
        description: 'Allow ssh access to ec2 instance and traffic to tgi inference endpoint',
        allowAllOutbound: true,
        disableInlineRules: true
      });

      ec2SG.addIngressRule(
        ec2.Peer.ipv4(vpcStack.cidr),
        ec2.Port.tcp(22),
        'Allow ssh traffic to ec2',
      );

      ec2SG.addIngressRule(
        ec2.Peer.ipv4(vpcStack.cidr),
        ec2.Port.tcp(8080),
        'Allow traffic to inference endpoint',
      );
      
      // Find the Deep Learning Base GPU AMI (Ubuntu 20.04)
      const dlami = ec2.MachineImage.lookup({
        name: 'Deep Learning Base GPU AMI (Ubuntu 20.04)*',
        owners: ['amazon'],
      });

      // Create a keypair for the instance 
      const ec2KeyPair = new ec2.CfnKeyPair(this, 'student-advising-tgi-keypair', {
        keyName: 'student-advising-ec2-tgi-key',
      });

      // Create the instance
      const ec2Instance = new ec2.Instance(this, 'student-advising-tgi-inference', {
        vpc: vpc,
        vpcSubnets: {
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
        securityGroup: ec2SG,
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.G4DN, ec2.InstanceSize.XLARGE),
        machineImage: dlami,
        blockDevices: [
          {
            deviceName: '/dev/sda1',
            volume: ec2.BlockDeviceVolume.ebs(100),
          }
        ],
        requireImdsv2: true,
        associatePublicIpAddress: false,
        keyName: ec2KeyPair.keyName
      });

      // Load the startup script
      const startupScript = readFileSync('./lib/ec2-tgi-startup.sh', 'utf8');
      ec2Instance.addUserData(startupScript);

      this.ENDPOINT_NAME = ec2Instance.instancePrivateIp + ':8080';
    } else {
      this.ENDPOINT_NAME = "none";
      this.ENDPOINT_TYPE = "none";
    }

    // Create the SSM parameter with the string value of the sagemaker inference endpoint name
    new ssm.StringParameter(this, "EndpointNameParameter", {
      parameterName: "/student-advising/generator/ENDPOINT_NAME",
      stringValue: this.ENDPOINT_NAME,
    });

    // Create the SSM parameter with the name of the generator model
    new ssm.StringParameter(this, "GeneratorModelNameParameter", {
      parameterName: "/student-advising/generator/MODEL_NAME",
      stringValue: MODEL_NAME,
    });

    // Create the SSM parameter with the type of the generator model
    new ssm.StringParameter(this, "GeneratorModelTypeParameter", {
      parameterName: "/student-advising/generator/ENDPOINT_TYPE",
      stringValue: this.ENDPOINT_TYPE,
    });

    // Create the SSM parameter with the type of the retriever
    new ssm.StringParameter(this, "RetrieverNameParameter", {
      parameterName: "/student-advising/retriever/RETRIEVER_NAME",
      stringValue: config.retriever_type,
    });

    // Create the SSM parameter with the llm mode
    new ssm.StringParameter(this, "LlmMode", {
      parameterName: "/student-advising/LLM_MODE",
      stringValue: ((config.llm_mode == "none") ? 'false' : 'true'),
    });
  }
}
