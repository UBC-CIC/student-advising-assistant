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
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3Deploy from "aws-cdk-lib/aws-s3-deployment";
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';

// https://github.com/aws-samples/aws-elastic-beanstalk-hardened-security-cdk-sample/blob/main/lib/elastic_beanstalk_cdk_project-stack.ts
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
          DB_SECRET_NAME: databaseStack.secretPathAdminName,
        },
        vpc: vpcStack.vpc,
        code: lambda.Code.fromAsset("./lambda/store_feedback"),
        layers: [inferenceStack.psycopg2_layer],
        role: inferenceStack.lambda_rds_role,
      }
    );

    const fetchFeedbackLambda = new lambda.Function(
      this,
      "student-advising-fetch-feedback",
      {
        functionName: "student-advising-fetch-feedback-logs",
        runtime: lambda.Runtime.PYTHON_3_9,
        handler: "fetch_feedback.lambda_handler",
        timeout: cdk.Duration.seconds(300),
        memorySize: 512,
        environment: {
          DB_SECRET_NAME: databaseStack.secretPathAdminName,
          BUCKET_PARAM_NAME: 	inferenceStack.S3_SSM_PARAM_NAME
        },
        vpc: vpcStack.vpc,
        code: lambda.Code.fromAsset("./lambda/fetch_feedback"),
        layers: [inferenceStack.psycopg2_layer],
        role: inferenceStack.lambda_rds_role,
      }
    );
    
    const beanstalkBucketName = `elasticbeanstalk-${this.region}-${this.account}`;
    let deploymentBucket = s3.Bucket.fromBucketName(
      this,
      "student-advising-EBBucket",
      beanstalkBucketName
    );

    // Check if the bucket exists
    if (!deploymentBucket.bucketName) {
      // If the bucket doesn't exist, create it
      // Create an encrypted bucket for beanstalk deployments and log storage
      // S3 Bucket needs a specific format for deployment: https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.S3.html
      // elasticbeanstalk-region-accountId
      deploymentBucket = new s3.Bucket(this, "student-advising-EBBucket", {
        bucketName: beanstalkBucketName,
        encryption: s3.BucketEncryption.S3_MANAGED,
        blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        publicReadAccess: false,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        enforceSSL: true,
      });
    }

    console.log("path is:" + this.zipFilePath);
    // Upload the deployment beanstalk app ZIP file to the bucket 
    const appDeploymentZip = new s3Deploy.BucketDeployment(this, "student-advising-elb-zip", {
      sources: [s3Deploy.Source.asset(this.zipFilePath)],
      destinationBucket: deploymentBucket,
      extract: false // we want to upload the whole zip to s3, not extract the zip on s3
    });

    /*
    - EC2 Instance Profile role for Beanstalk App
    - this role will be used for both task role and task execution role
    - Clarification: creates an IAM role with the logical ID ec2-iam-role, 
                     but the actual name of the role in AWS will be generated 
                     automatically by AWS CDK. The naming convention used by CDK is 
                     <StackName>-<LogicalID>-<RandomString>.

    */
    const ec2IamRole = new iam.Role(this, "ec2-iam-role", {
      assumedBy: new iam.ServicePrincipal("ec2.amazonaws.com"),
      description: "Role serves as EC2 Instance Profile",
    });

    // Add managed policies to the role
    const managedPolicies = [
      "service-role/AWSLambdaRole",
      "AmazonSSMManagedInstanceCore",
      "AWSElasticBeanstalkMulticontainerDocker",
      "AWSElasticBeanstalkWebTier",
      "AWSElasticBeanstalkWorkerTier",
      "SecretsManagerReadWrite",
      "AmazonSSMReadOnlyAccess",
      "AmazonSageMakerFullAccess",
      "AmazonS3FullAccess",
    ];

    managedPolicies.forEach((policy) => {
      ec2IamRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName(policy));
    });

    // Add custom inline policy for Bedrock access
    const customBedrockPolicy = new iam.Policy(this, "custom-bedrock-policy", {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["bedrock:InvokeModel"],
          resources: [
            "arn:aws:bedrock:" + this.region + "::foundation-model/meta.llama3-70b-instruct-v1:0",
            "arn:aws:bedrock:" + this.region + "::foundation-model/meta.llama3-8b-instruct-v1:0",
            "arn:aws:bedrock:" + this.region + "::foundation-model/mistral.mistral-7b-instruct-v0:2",
            "arn:aws:bedrock:" + this.region + "::foundation-model/mistral.mistral-large-2402-v1:0",
            "arn:aws:bedrock:" + this.region + "::foundation-model/amazon.titan-embed-text-v2:0",
          ],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["ssm:DescribeParameters", "secretsmanager:ListSecrets"],
          resources: ["*"],
        }),
      ],
    });

    ec2IamRole.attachInlinePolicy(customBedrockPolicy);

    const instanceProfName = `beanstalk-ec2-instance-profile-${this.region}`;
    // Create a new Instance Profile with the desired IAM Role
    let instanceProfile = new iam.InstanceProfile(this, instanceProfName, {
      role: ec2IamRole,
      instanceProfileName: instanceProfName,
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
          s3Bucket: deploymentBucket.bucketName,
          s3Key: cdk.Fn.select(0, appDeploymentZip.objectKeys),
        },
      }
    );
    appVersionProps.node.addDependency(appDeploymentZip);  

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const cnamePrefix = "student-advising-demo"; // Prefix for the web app's url
    const elbEnv = new elasticbeanstalk.CfnEnvironment(this, "Environment", {
      environmentName: "student-advising-demo-app-env",
      cnamePrefix: cnamePrefix,
      description: "Docker environment for Python Flask application",
      applicationName: app.applicationName || appName,
      solutionStackName: "64bit Amazon Linux 2 v4.0.0 running Docker",
      optionSettings: [
        // https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "InstanceType",
          value: "t3.medium",
        },
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "DisableIMDSv1",
          value: "true",
        },
        {
          namespace: "aws:autoscaling:launchconfiguration",
          optionName: "IamInstanceProfile",
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
          namespace: "aws:elasticbeanstalk:command",
          optionName: "DeploymentPolicy",
          value: "Rolling",
        },
        {
          namespace: "aws:elasticbeanstalk:environment",
          optionName: "LoadBalancerType",
          value: "application",
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
            .selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_ISOLATED })
            .subnetIds.join(","),
        },
        {
          namespace: "aws:ec2:vpc",
          optionName: "ELBSubnets",
          value: vpcStack.vpc
            .selectSubnets({ subnetType: ec2.SubnetType.PUBLIC })
            .subnetIds.join(","),
        },
        {
          namespace: "aws:ec2:vpc",
          optionName: "AssociatePublicIpAddress",
          value: "false",
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
        {
          namespace: "aws:elasticbeanstalk:managedactions",
          optionName: "ManagedActionsEnabled",
          value: "true",
        },
        {
          namespace: "aws:elasticbeanstalk:managedactions",
          optionName: "PreferredStartTime",
          value: "Sun:01:00",
        },
        {
          namespace: "aws:elasticbeanstalk:managedactions",
          optionName: "ServiceRoleForManagedUpdates",
          value: "AWSServiceRoleForElasticBeanstalkManagedUpdates",
        },
        {
          namespace: "aws:elasticbeanstalk:managedactions:platformupdate",
          optionName: "UpdateLevel",
          value: "minor",
        },
      ],
      // This line is critical - reference the label created in this same stack
      versionLabel: appVersionProps.ref,
    });
    // Also very important - make sure that `app` exists before creating an app version
    appVersionProps.addDependency(app);

    const webAcl = new wafv2.CfnWebACL(this, 'WebAcl', {
      description: 'WAF for Student Advising ALB',
      scope: 'REGIONAL',
      defaultAction: { allow: {} },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'studentAdvising-firewall',
        sampledRequestsEnabled: true,
      },
      rules: [
        {
          name: 'AWS-AWSManagedRulesAmazonIpReputationList',
          priority: 0,
          statement: {
            managedRuleGroupStatement: {
              name: 'AWSManagedRulesAmazonIpReputationList',
              vendorName: 'AWS'
            }
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWS-AWSManagedRulesAmazonIpReputationList'
          }
        },
        {
          name: 'AWS-AWSManagedRulesCommonRuleSet',
          priority: 1,
          statement: {
            managedRuleGroupStatement: {
              name: 'AWSManagedRulesCommonRuleSet',
              vendorName: 'AWS'
            }
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWS-AWSManagedRulesCommonRuleSet'
          }
        },
        {
          name: 'AWS-AWSManagedRulesKnownBadInputsRuleSet',
          priority: 2,
          statement: {
            managedRuleGroupStatement: {
              name: 'AWSManagedRulesKnownBadInputsRuleSet',
              vendorName: 'AWS'
            }
          },
          overrideAction: { none: {} },
          visibilityConfig: {
            sampledRequestsEnabled: true,
            cloudWatchMetricsEnabled: true,
            metricName: 'AWS-AWSManagedRulesKnownBadInputsRuleSet'
          }
        },
        {
          name: "LimitRequests1000",
          priority: 3,
          action: {
            block: {},
          },
          statement: {
            rateBasedStatement: {
              limit: 1000, // 1000 requests per 5 minutes
              aggregateKeyType: "IP",
            },
          },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: "LimitRequests1000",
            sampledRequestsEnabled: true,
          },
        },
      ],
    });

    const albArn = cdk.Fn.join('', [
      'arn:aws:elasticloadbalancing:',
      this.region,
      ':',
      this.account,
      ':loadbalancer/app/',
      elbEnv.attrEndpointUrl,
    ]);

    new wafv2.CfnWebACLAssociation(this, 'WebAclAssociation', {
      resourceArn: albArn,
      webAclArn: webAcl.attrArn,
    });

    elbEnv.node.addDependency(webAcl);

    // Create the SSM parameter with the url of the elastic beanstalk web app
    new ssm.StringParameter(this, "BeanstalkAppUrlParameter", {
      parameterName: "/student-advising/BEANSTALK_URL",
      stringValue: cnamePrefix + "." + this.region + ".elasticbeanstalk.com",
    });
  }
}
