import boto3

# Define AccessKeyId and SecretAccessKey as variables
AccessKeyId = ""
SecretAccessKey = ""

def assume_role(role_arn, session_name):
    # Create an STS client using the specified Access Key and Secret Key
    sts_client = boto3.client(
        'sts',
        aws_access_key_id=AccessKeyId,
        aws_secret_access_key=SecretAccessKey
    )
    
    try:
        # Call assume_role to get temporary security credentials, with a 15-minute expiration
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=900  # 900 seconds is the minimum, which is 15 minutes
        )

        # Extract the credentials
        credentials = response['Credentials']

        print(f"Access Key: {credentials['AccessKeyId']}")
        print(f"Secret Access Key: {credentials['SecretAccessKey']}")
        print(f"Session Token: {credentials['SessionToken']}")
        print(f"Expiration: {credentials['Expiration']}")

    except Exception as e:
        print(f"Error assuming role: {e}")

if __name__ == "__main__":
    role_arn = "arn:aws:iam::370296042006:role/custom-role-StartFaceLivenessSession"
    session_name = "face_liveness_session"  # You can customize this session name
    
    assume_role(role_arn, session_name)