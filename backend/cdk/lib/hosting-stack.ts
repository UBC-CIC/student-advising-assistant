import * as cdk from "aws-cdk-lib";
import * as elasticbeanstalk from "aws-cdk-lib/aws-elasticbeanstalk";
import * as s3assets from "aws-cdk-lib/aws-s3-assets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as path from "path";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { VpcStack } from "./vpc-stack";
import { DatabaseStack } from "./database-stack";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { InferenceStack } from "./inference-stack";
import * as ec2 from "aws-cdk-lib/aws-ec2";

export class HostingStack extends cdk.Stack {
  private readonly zipFileName: string = "demo-app.zip";
  private readonly zipFilePath: string = path.join(
    __dirname,
    "..",
    "..",
    "..",
    this.zipFileName
  );

  constructor(
    scope: cdk.App,
    id: string,
    vpcStack: VpcStack,
    databaseStack: DatabaseStack,
    inferenceStack: InferenceStack,
    props?: cdk.StackProps
  ) {
    super(scope, id, props);

    const storeFeedbackLambda = new lambda.Function(
      this,
      "student-advising-store-feedback",
      {
        functionName: "student-advising-store-feedback-to-db",
        runtime: lambda.Runtime.PYTHON_3_9,
        handler: "store_feedback_to_db.lambda_handler",
        timeout: cdk.Duration.seconds(300),
        memorySize: 512,
        environment: {
          DB_SECRET_NAME: databaseStack.secretPath,
        },
        vpc: vpcStack.vpc,
        code: lambda.Code.fromAsset("./lambda/store_feedback"),
        layers: [inferenceStack.psycopg2_layer],
        role: inferenceStack.lambda_rds_role,
      }
    );

    console.log("path is:" + this.zipFilePath);
    // Construct an S3 asset from the ZIP located from directory up.
    const elbZipArchive = new s3assets.Asset(this, "student-advising-elb-zip", {
      path: this.zipFilePath,
    });

    // EC2 Instance Profile role for Beanstalk App
    // this role will be used for both task role and task execution role
    const ec2IamRole = new iam.Role(this, "ec2-iam-role", {
      assumedBy: new iam.ServicePrincipal("ec2.amazonaws.com"),
      description: "Role serves as EC2 Instance Profile",
    });
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonS3FullAccess")
    );
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaRole")
    );
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMReadOnlyAccess")
    );
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AWSElasticBeanstalkWebTier")
    );
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        "AWSElasticBeanstalkMulticontainerDocker"
      )
    );
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSageMakerFullAccess")
    );
    ec2IamRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName("SecretsManagerReadWrite")
    );

    const instanceProfile = new iam.CfnInstanceProfile(this, "beanstalk-ec2-instance-profile", {
      roles: [ec2IamRole.roleName],
      instanceProfileName: "beanstalk-ec2-instance-profile",
    });

    const appName = "student-advising-demo-app";
    const app = new elasticbeanstalk.CfnApplication(
      this,
      "student-advising-app",
      {
        applicationName: appName,
        description: "Demo flask app provisioned with AWS CDK",
      }
    );

    // Create an app version from the S3 asset defined above
    // The S3 "putObject" will occur first before CF generates the template
    const appVersionProps = new elasticbeanstalk.CfnApplicationVersion(
      this,
      "AppVersion",
      {
        applicationName: appName,
        sourceBundle: {
          s3Bucket: elbZipArchive.s3BucketName,
          s3Key: elbZipArchive.s3ObjectKey,
        },
      }
    );

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const cnamePrefix = "student-advising-demo"; // Prefix for the web app's url
    const elbEnv = new elasticbeanstalk.CfnEnvironment(this, "Environment", {
      environmentName: "student-advising-demo-app-env",
      cnamePrefix: cnamePrefix,
      description: "Docker environment for Python Flask application",
      applicationName: app.applicationName || appName,
      solutionStackName: "64bit Amazon Linux 2 v3.6.0 running Docker",
      optionSettings: [
        // https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "InstanceType",
          value: "t3.medium",
        },
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "IamInstanceProfile",
          // Here you could reference an instance profile by ARN (e.g. myIamInstanceProfile.attrArn)
          // For the default setup, leave this as is (it is assumed this role exists)
          // https://stackoverflow.com/a/55033663/6894670
          value: instanceProfile.instanceProfileName,
        },
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "RootVolumeType",
          value: "gp2",
        },
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "RootVolumeSize",
          value: "30",
        },
        {
          namespace: "aws:ec2:vpc",
          optionName: "VPCId",
          value: vpcStack.vpc.vpcId,
        },
        {
          namespace: "aws:ec2:vpc",
          optionName: "Subnets",
          value: vpcStack.vpc
            .selectSubnets({ subnetType: ec2.SubnetType.PUBLIC })
            .subnetIds.join(","),
        },
        {
          namespace: "aws:elasticbeanstalk:application:environment",
          optionName: "AWS_DEFAULT_REGION",
          value: this.region,
        },
        {
          namespace: "aws:elasticbeanstalk:application:environment",
          optionName: "FEEDBACK_LAMBDA",
          value: storeFeedbackLambda.functionName,
        },
        {
          namespace: "aws:elasticbeanstalk:cloudwatch:logs",
          optionName: "StreamLogs",
          value: "true",
        },
        {
          namespace: "aws:elasticbeanstalk:cloudwatch:logs",
          optionName: "DeleteOnTerminate",
          value: "true",
        },
        {
          namespace: "aws:elasticbeanstalk:cloudwatch:logs",
          optionName: "RetentionInDays",
          value: "365",
        },
      ],
      // This line is critical - reference the label created in this same stack
      versionLabel: appVersionProps.ref,
    });
    elbEnv.addDependency(instanceProfile);
    // Also very important - make sure that `app` exists before creating an app version
    appVersionProps.addDependency(app);

    // Create the SSM parameter with the url of the elastic beanstalk web app
    // const regionLongName: string = ssm.StringParameter.valueFromLookup(
    //   this,
    //   `/aws/service/global-infrastructure/regions/${this.region}/longName`
    // );

    new ssm.StringParameter(this, "S3BucketNameParameter", {
      parameterName: "/student-advising/BEANSTALK_URL",
      stringValue: cnamePrefix + "." + this.region + ".elasticbeanstalk.com",
    });
  }
}
