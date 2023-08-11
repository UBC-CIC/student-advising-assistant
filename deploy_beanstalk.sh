#!/usr/bin/env bash

# shell script argument parser from: https://unix.stackexchange.com/a/353639
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
 
    KEY_LENGTH=${#KEY}
    VALUE="${ARGUMENT:$KEY_LENGTH+1}"
    export "$KEY"=$VALUE
done

# AWS_PROFILE_NAME=${1}
# AWS_PROFILE_REGION=${2}
# BUNDLE_NAME=${3}
# BUNDLE_VER=${4}
# BEANSTALK_BUCKET=${5}
# APP_NAME=${6}
# APP_ENV_NAME=${7}

echo "The AWS profile is: $AWS_PROFILE_NAME"
echo "The AWS profile region is: $AWS_PROFILE_REGION"
echo "The bundle zip file name is: $BUNDLE_NAME"
echo "The deployment bundle version label is: $BUNDLE_VER"
echo "The S3 bucket for AWS Elastic Beanstalk app deployment file is: $BEANSTALK_BUCKET"
echo "The name of the Beanstalk app: $APP_NAME"
echo "The environment name of the Beanstalk app: $APP_ENV_NAME"

COMBINE_FILENAME="$BUNDLE_NAME-$BUNDLE_VER.zip"

if [ -f "$COMBINE_FILENAME" ]; then
    echo "Zip file exists: $COMBINE_FILENAME"
    options="Overwrite Keep-Existing Quit"
    PS3="Select any option: "
    select o in $options; do
        if [ $o == 'Quit' ]; then
            echo "Exiting the script."
            exit 0
        elif [ $o == 'Overwrite' ]; then
            echo "Create new zip file with same name, overwriting $COMBINE_FILENAME..."
            zip -r $COMBINE_FILENAME aws_helpers/ flask_app/ Dockerfile -x "*/.*" -x ".*" || echo "Failed to zip file"
            echo "Created new zip bundle $COMBINE_FILENAME"
        fi
        break
    done
else
    echo "Zip file does not exist: $COMBINE_FILENAME"
    echo "This process will create a new zip bundle: $COMBINE_FILENAME"
    # Prompt user with Y/n (Y is the default option)
    read -rp "Do you want to continue? (Y/n): " -e choice

    # If no input provided, use the default value "Y"
    choice="${choice:-Y}"

    # Check the user's response
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        echo "Continuing the script..."
        # zip -r $COMBINE_FILENAME aws_helpers/ flask_app/ Dockerfile -x "*/.*" -x ".*"
        echo "Created new zip bundle $COMBINE_FILENAME"
    else
        echo "Exiting the script."
        exit 0
    fi
fi

echo "Deploying the zip bundle to the cloud (with POTENTIALLY BREAKING CHANGEs)?"
options="Yes Quit"
PS3="Select 1 option: "
select o in $options; do
    if [ $o == 'Quit' ]; then
        echo "Exiting the script."
        exit 1
    fi

    # Uploading to S3
    echo "Uploading the bundle $COMBINE_FILENAME to S3 bucket with path s3://$BEANSTALK_BUCKET/$COMBINE_FILENAME ..."
    aws s3 cp $COMBINE_FILENAME s3://$BEANSTALK_BUCKET/$COMBINE_FILENAME --profile $AWS_PROFILE_NAME --region $AWS_PROFILE_REGION

    # Creating application version
    echo "Creating application version $BUNDLE_VER for app $APP_NAME, in region $AWS_PROFILE_REGION ..."
    aws elasticbeanstalk create-application-version --application-name $APP_NAME \
        --version-label $BUNDLE_VER \
        --source-bundle S3Bucket=$BEANSTALK_BUCKET,S3Key=$COMBINE_FILENAME \
        --profile $AWS_PROFILE_NAME \
        --region $AWS_PROFILE_REGION
    
    # Update the environment with the new bundle
    echo "Updating environment $APP_ENV_NAME of app $APP_NAME ..."
    aws elasticbeanstalk update-environment --application-name $APP_NAME \
        --environment-name $APP_ENV_NAME \
        --version-label $BUNDLE_VER \
        --profile $AWS_PROFILE_NAME \
        --region $AWS_PROFILE_REGION

    echo "Deployment successful. Exiting the script"
    exit 0
done

# aws elasticbeanstalk create-application-version --application-name my-app --version-label 12345 --source-bundle S3Bucket="mybucket",S3Key="deploy.zip"
# aws elasticbeanstalk update-environment --application-name my-app --environment-name MyApp-env --version-label 12345
