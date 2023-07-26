import * as cdk from "aws-cdk-lib";
import { Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { aws_rds as rds } from "aws-cdk-lib";
import { VpcStack } from "./vpc-stack";
import * as logs from "aws-cdk-lib/aws-logs";
import * as sm from "aws-cdk-lib/aws-secretsmanager";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as triggers from "aws-cdk-lib/triggers";

export class DatabaseStack extends Stack {
  public readonly dbInstance: rds.DatabaseInstance;
  public readonly secretPath: string;
  public readonly rdsProxyEndpoint: string;

  constructor(
    scope: Construct,
    id: string,
    vpcStack: VpcStack,
    props?: StackProps
  ) {
    super(scope, id, props);

    this.secretPath = "student-advising/credentials/RDSCredentials";

    // Database secret with customized username retrieve at deployment time
    const dbUsername = sm.Secret.fromSecretNameV2(
      this,
      "student-advising-dbUsername",
      "student-advising-dbUsername"
    );

    // Define the postgres database
    this.dbInstance = new rds.DatabaseInstance(this, "student-advising", {
      vpc: vpcStack.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15_2, // earliest support for pgvector
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.BURSTABLE3,
        ec2.InstanceSize.MICRO
      ),
      credentials: rds.Credentials.fromUsername(
        dbUsername.secretValueFromJson("username").unsafeUnwrap(),
        {
          secretName: this.secretPath,
        }
      ),
      multiAz: true,
      allocatedStorage: 100,
      maxAllocatedStorage: 115,
      allowMajorVersionUpgrade: false,
      autoMinorVersionUpgrade: true,
      backupRetention: cdk.Duration.days(7),
      deleteAutomatedBackups: true,
      deletionProtection: true,
      databaseName: "studentadvisingpostgresql",
      publiclyAccessible: false,
      cloudwatchLogsRetention: logs.RetentionDays.INFINITE,
      storageEncrypted: true, // storage encryption at rest
      monitoringInterval: cdk.Duration.seconds(60), // enhanced monitoring interval
    });

    this.dbInstance.connections.securityGroups.forEach(function (
      securityGroup
    ) {
      // 10.0.0.0/16 match the cidr range in vpc stack
      securityGroup.addIngressRule(
        ec2.Peer.ipv4(vpcStack.cidr),
        ec2.Port.tcp(5432),
        "Postgres Ingress"
      );
    });

    // const rdsProxy = new rds.DatabaseProxy(this, "student-advising-RDSProxy", {
    //   proxyTarget: rds.ProxyTarget.fromInstance(this.dbInstance),
    //   secrets: [this.dbInstance.secret!],
    //   vpc: vpcStack.vpc,
    //   securityGroups: this.dbInstance.connections.securityGroups,
    //   // securityGroups: [ec2.SecurityGroup.fromSecurityGroupId(this, 'VpcDefaultSecurityGroup', vpcStack.vpc.vpcDefaultSecurityGroup)],
    //   requireTLS: false,
    // });

    // const dbProxyRole = new iam.Role(this, "DBProxyRole", {
    //   assumedBy: new iam.AccountPrincipal(this.account),
    // });
    // rdsProxy.grantConnect(dbProxyRole, "admin"); // Grant the role connection access to the DB Proxy for database user 'admin'.

    // this.rdsProxyEndpoint = rdsProxy.endpoint;
  }
}
