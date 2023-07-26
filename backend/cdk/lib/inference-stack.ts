import { Stack, StackProps, Duration, RemovalPolicy } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as iam from "aws-cdk-lib/aws-iam";
import { ManagedPolicy } from "aws-cdk-lib/aws-iam";
import { NatProvider } from "aws-cdk-lib/aws-ec2";
import { VpcStack } from "./vpc-stack";
import * as ecs from "aws-cdk-lib/aws-ecs";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import * as path from "path";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as triggers from "aws-cdk-lib/triggers";
import { DatabaseStack } from "./database-stack";
import * as ecsPatterns from "aws-cdk-lib/aws-ecs-patterns";
import * as events from 'aws-cdk-lib/aws-events';
import * as s3 from "aws-cdk-lib/aws-s3";

export class InferenceStack extends Stack {
  constructor(
    scope: Construct,
    id: string,
    vpcStack: VpcStack,
    databaseStack: DatabaseStack,
    props?: StackProps
  ) {
    super(scope, id, props);

    const vpc = vpcStack.vpc;

    // Bucket for files related to inference
    const inferenceBucket = new s3.Bucket(
      this,
      "student-advising-s3bucket",
      {
        removalPolicy: RemovalPolicy.DESTROY,
        autoDeleteObjects: true,
        versioned: false,
        publicReadAccess: false,
        blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        encryption: s3.BucketEncryption.S3_MANAGED,
      }
    );

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
        "AmazonECSTaskExecutionRolePolicy"
      )
    );
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonS3FullAccess")
    );
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("SecretsManagerReadWrite")
    );
    ecsTaskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMFullAccess")
    );

    const fargateCluster = new ecs.Cluster(this, "datapipeline-cluster", {
      vpc: vpc,
      enableFargateCapacityProviders: true,
    });

    const ecsTaskDef = new ecs.FargateTaskDefinition(
      this,
      "datapipeline-taskdef",
      {
        cpu: 1024,
        memoryLimitMiB: 4096,
        taskRole: ecsTaskRole,
        executionRole: ecsTaskRole,
      }
    );
    ecsTaskDef.addContainer("datapipeline-containers", {
      image: ecs.ContainerImage.fromAsset(
        path.join(__dirname, "..", "..", "..", "document_scraping")
      ),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "student-advising",
        logRetention: RetentionDays.ONE_YEAR,
      }),
      environment: {
        BUCKET_NAME: inferenceBucket.bucketName,
      },
    });

    const fargateService = new ecs.FargateService(this, "fargate-service", {
      cluster: fargateCluster,
      taskDefinition: ecsTaskDef,
      securityGroups: [clusterSg],
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
    });

    // Create a scheduled fargate task that runs at 8:00 UTC on the first of every month
    const scheduledFargateTask = new ecsPatterns.ScheduledFargateTask(this, 'ScheduledFargateTask', {
      cluster: fargateCluster,
      scheduledFargateTaskDefinitionOptions: {
        taskDefinition: ecsTaskDef
      },
      securityGroups: [clusterSg],
      schedule: events.Schedule.cron({
        minute: '0',
        hour: '0',
        month: '*',
        weekDay: 'SAT'
      }),
      subnetSelection: {subnetType: ec2.SubnetType.PRIVATE_ISOLATED},
    });

    // this role will be used for both task role and task execution role
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
      iam.ManagedPolicy.fromAwsManagedPolicyName("SSMReadOnlyAccess")
    );

    // The layer containing the psycopg2 library
    const psycopg2 = new lambda.LayerVersion(this, "psycopg2", {
      code: lambda.Code.fromAsset("layers/psycopg2.zip"),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
      description: "psycopg2 library for connecting to the PostgreSQL database",
    });

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
      }
    );

    const storeFeedbackLambda = new lambda.Function(
      this,
      "student-advising-store-feedback",
      {
        functionName: "student-advising-store-feedback-to-db",
        runtime: lambda.Runtime.PYTHON_3_9,
        handler: "store_feedback_to_db.lambda_handler",
        timeout: Duration.seconds(300),
        memorySize: 512,
        environment: {
          DB_SECRET_NAME: databaseStack.secretPath,
        },
        vpc: vpcStack.vpc,
        code: lambda.Code.fromAsset("./lambda/store_feedback"),
        layers: [psycopg2],
      }
    );
  }
}
