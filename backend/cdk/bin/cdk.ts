#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { VpcStack } from '../lib/vpc-stack';
import { DatabaseStack } from '../lib/database-stack';
import { InferenceStack } from '../lib/inference-stack';
import { HostingStack } from '../lib/hosting-stack';

const app = new cdk.App();
  /* If you don't specify 'env', this stack will be environment-agnostic.
   * Account/Region-dependent features and context lookups will not work,
   * but a single synthesized template can be deployed anywhere. */

  /* Uncomment the next line to specialize this stack for the AWS Account
   * and Region that are implied by the current CLI configuration. */
  // env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },

  /* Uncomment the next line if you know exactly what Account and Region you
   * want to deploy the stack to. */
  // env: { account: '123456789012', region: 'us-east-1' },

  /* For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html */

console.log("App region is ", app.region)
// const identifier = "ai-assist"

const region = process.env.CDK_DEFAULT_REGION
// const region = "us-west-2"

const vpcStack = new VpcStack(app, "student-advising-VpcStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    // region: process.env.CDK_DEFAULT_REGION,
    region: region
  },
});

const databaseStack = new DatabaseStack(app, "student-advising-DatabaseStack", vpcStack, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    // region: process.env.CDK_DEFAULT_REGION
    region: region
  },
}); 
databaseStack.addDependency(vpcStack)

const inferenceStack = new InferenceStack(app, "InferenceStack", vpcStack, databaseStack, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    // region: process.env.CDK_DEFAULT_REGION
    region: region
  }
});

const hostingStack = new HostingStack(app, "HostingStack", vpcStack, databaseStack, inferenceStack, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    // region: process.env.CDK_DEFAULT_REGION
    region: region
  }
});