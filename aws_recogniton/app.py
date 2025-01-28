from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
import boto3
import os
from logging import getLogger



# AWS Credentials and Region
AWS_ACCESS_KEY = ""
AWS_SECRET_ACCESS_KEY = ""
AWS_REGION = "us-west-2"  # Modify this to the appropriate region
S3_BUCKET = "face-service-images-us-west-2"  # S3 bucket name
AWS_ROLE_ARN = "arn:aws:iam::977098990559:policy/custom-policy-StartFaceLivenessSession"
# Create logger
logger = getLogger('rekognition_log')

# Define FaceLivenessError
class FaceLivenessError(Exception):
    '''
    Represents an error due to Face Liveness Issue.
    '''
    pass

# Initialize FastAPI app
app = FastAPI()

# Initialize AWS Rekognition and STS client with AWS credentials
rekognition_client = boto3.client(
    "rekognition", 
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)
sts_client = boto3.client(
    "sts", 
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# Define Pydantic model for request body
class CreateFaceLivenessSessionRequest(BaseModel):
    image: str  # S3 URL for the image to analyze
    session_name: Optional[str] = None

def get_temp_credentials(session_name):
    '''
    Get temporary AWS credentials using AssumeRole
    '''
    try:
        # Call assume_role to get temporary security credentials
        response = sts_client.assume_role(
            RoleArn=os.getenv("AWS_ROLE_ARN"),
            RoleSessionName=session_name,
            DurationSeconds=900  # 15 minutes
        )
        # Return credentials from the response
        return response['Credentials']
    except sts_client.exceptions.AccessDeniedException:
        logger.error('Access Denied Error')
        raise FaceLivenessError('AccessDeniedError')
    except sts_client.exceptions.InternalServerError:
        logger.error('InternalServerError')
        raise FaceLivenessError('InternalServerError')
    except sts_client.exceptions.InvalidParameterException:
        logger.error('InvalidParameterException')
        raise FaceLivenessError('InvalidParameterException')
    except sts_client.exceptions.ThrottlingException:
        logger.error('ThrottlingException')
        raise FaceLivenessError('ThrottlingException')

@app.get("/create_liveness_session")
async def create_face_liveness_session(request: CreateFaceLivenessSessionRequest):
    try:
        # Generate a unique ClientRequestToken if not provided
        client_request_token = str(uuid.uuid4())  # Automatically generate a token

        # Prepare S3 image URL
        s3_url = request.image
        image_info = {
            "S3Object": {
                "Bucket": S3_BUCKET            }
        }

        # Additional settings for Rekognition API
        rekognition_settings = {
            "ClientRequestToken": client_request_token,
            "Settings": {
                "AuditImagesLimit": 1,
                "OutputConfig": {
                    "S3Bucket": S3_BUCKET
                }
            }
        }

        # Get temporary credentials
        credentials = get_temp_credentials(request.session_name or client_request_token)

        # Call Rekognition to create the face liveness session
        response = rekognition_client.create_face_liveness_session(
            Image=image_info,
            ClientRequestToken=rekognition_settings["ClientRequestToken"],
            SessionName=request.session_name,
            Settings=rekognition_settings["Settings"]
        )
        
        return response

    except FaceLivenessError as e:
        # Handle known exceptions
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle unexpected exceptions
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/session_result/{session_id}")
async def get_session_result(session_id: str):
    '''
    Get results of the face liveness session.
    '''
    try:
        # Call Rekognition to get session results
        response = rekognition_client.get_face_liveness_session_results(
            SessionId=session_id
        )
        return response

    except rekognition_client.exceptions.AccessDeniedException:
        logger.error('Access Denied Error')
        raise HTTPException(status_code=403, detail='Access Denied Error')
    except rekognition_client.exceptions.SessionNotFoundException:
        logger.error('Session Not Found Error')
        raise HTTPException(status_code=404, detail='Session Not Found')
    except rekognition_client.exceptions.InternalServerError:
        logger.error('Internal Server Error')
        raise HTTPException(status_code=500, detail='Internal Server Error')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Define FaceLivenessError
class FaceLivenessError(Exception):
    '''
    Represents an error due to AWS STS Assume Role Issue.
    '''
    pass

# Initialize FastAPI app
app = FastAPI()

# Initialize AWS STS client with AWS credentials
sts_client = boto3.client(
    "sts", 
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# Define Pydantic model for request body
class GenerateSTSRequest(BaseModel):
    session_name: str  # Name for the session to generate credentials

# Function to get temporary security credentials
def get_temp_credentials(session_name):
    '''
    Get temporary AWS credentials using AssumeRole
    '''
    try:
        # Call assume_role to get temporary security credentials
        response = sts_client.assume_role(
            RoleArn=AWS_ROLE_ARN,  # Fetch the ARN from environment variable
            RoleSessionName=session_name,
            DurationSeconds=900  # 900 seconds is the minimum, which is 15 minutes
        )
        # Return credentials from the response
        return response['Credentials']
    except sts_client.exceptions.AccessDeniedException:
        logger.error('Access Denied Error')
        raise FaceLivenessError('AccessDeniedError')
    except sts_client.exceptions.InternalServerError:
        logger.error('InternalServerError')
        raise FaceLivenessError('InternalServerError')
    except sts_client.exceptions.InvalidParameterException:
        logger.error('InvalidParameterException')
        raise FaceLivenessError('InvalidParameterException')
    except sts_client.exceptions.ThrottlingException:
        logger.error('ThrottlingException')
        raise FaceLivenessError('ThrottlingException')

# Define /generateSTS endpoint to get temporary AWS credentials
@app.post("/generateSTS")
async def generate_sts(request: GenerateSTSRequest):
    try:
        # Call get_temp_credentials to generate temporary credentials
        credentials = get_temp_credentials(request.session_name)

        # Return the credentials
        return {
            "AccessKeyId": credentials["AccessKeyId"],
            "SecretAccessKey": credentials["SecretAccessKey"],
            "SessionToken": credentials["SessionToken"],
            "Expiration": credentials["Expiration"].isoformat()
        }

    except FaceLivenessError as e:
        # Handle known exceptions
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle unexpected exceptions
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# To run the FastAPI server, use the following command:
# uvicorn app:app --reload


# To run the FastAPI server, use the following command:
# uvicorn app:app --reload