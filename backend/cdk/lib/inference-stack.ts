import { Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as iam from "aws-cdk-lib/aws-iam";
import { ManagedPolicy } from "aws-cdk-lib/aws-iam";
import { NatProvider } from "aws-cdk-lib/aws-ec2";
import { VpcStack } from "./vpc-stack";
import * as ecs from "aws-cdk-lib/aws-ecs";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import * as path from 'path';

export class InferenceStack extends Stack {
  constructor(
    scope: Construct,
    id: string,
    vpcStack: VpcStack,
    props?: StackProps
  ) {
    super(scope, id, props);

    const vpc = vpcStack.vpc;

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
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "..", "document_scraping")),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "student-advising",
        logRetention: RetentionDays.ONE_YEAR,
      }),
      environment: {
        BUCKET_NAME: "",
      },
    });

    const fargateService = new ecs.FargateService(this, "fargate-service", {
      cluster: fargateCluster,
      taskDefinition: ecsTaskDef,
      securityGroups: [clusterSg],
      vpcSubnets: { 
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED 
      },
    });
  }
}
