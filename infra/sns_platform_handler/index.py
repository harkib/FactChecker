"""
Custom resource handler for creating/deleting SNS Platform Application (APNs).
CloudFormation does not natively support AWS::SNS::PlatformApplication.

Creates two platform applications: APNS (production) and APNS_SANDBOX (development).
Production uses SecretArn; sandbox uses SecretArnSandbox if provided, else SecretArn.
Uses CDK Provider framework: return data on success, raise on failure.
Do NOT post to ResponseURL - the framework handles that.
"""
import json

import boto3


def handler(event, context):
    sns = boto3.client("sns")
    sm = boto3.client("secretsmanager")
    physical_resource_id = event.get("PhysicalResourceId")
    props = event.get("ResourceProperties", {})

    if event["RequestType"] == "Delete":
        if physical_resource_id and not physical_resource_id.startswith("could-not"):
            try:
                ids = json.loads(physical_resource_id)
                for arn in (ids.get("PlatformApplicationArn"), ids.get("PlatformApplicationArnSandbox")):
                    if arn:
                        sns.delete_platform_application(PlatformApplicationArn=arn)
            except json.JSONDecodeError:
                sns.delete_platform_application(PlatformApplicationArn=physical_resource_id)
        return {"PhysicalResourceId": physical_resource_id or "could-not-create"}

    # On Update: migrate from old single-ARN format if needed, then SetPlatformApplicationAttributes.
    if event["RequestType"] == "Update" and physical_resource_id and not physical_resource_id.startswith("could-not"):
        try:
            ids = json.loads(physical_resource_id)
            arn_prod = ids.get("PlatformApplicationArn")
            arn_sandbox = ids.get("PlatformApplicationArnSandbox")
        except json.JSONDecodeError:
            arn_prod = physical_resource_id
            arn_sandbox = None

        # Migration: create sandbox platform if we only have prod (old format)
        if not arn_sandbox:
            sandbox_secret_arn = props.get("SecretArnSandbox") or props["SecretArn"]
            secret_value = sm.get_secret_value(SecretId=sandbox_secret_arn)
            creds = json.loads(secret_value["SecretString"])
            create_attrs = {
                "PlatformCredential": creds["PlatformCredential"],
                "PlatformPrincipal": creds["PlatformPrincipal"],
                "ApplePlatformTeamID": creds["ApplePlatformTeamID"],
                "ApplePlatformBundleID": creds["ApplePlatformBundleID"],
            }
            if props.get("SuccessFeedbackRoleArn"):
                create_attrs["SuccessFeedbackRoleArn"] = props["SuccessFeedbackRoleArn"]
            if props.get("FailureFeedbackRoleArn"):
                create_attrs["FailureFeedbackRoleArn"] = props["FailureFeedbackRoleArn"]
            if props.get("SuccessFeedbackSampleRate") is not None:
                create_attrs["SuccessFeedbackSampleRate"] = str(props["SuccessFeedbackSampleRate"])
            name = props.get("Name", "factchecker-ios-apns")
            resp = sns.create_platform_application(
                Name=f"{name}-sandbox",
                Platform="APNS_SANDBOX",
                Attributes=create_attrs,
            )
            arn_sandbox = resp["PlatformApplicationArn"]
            physical_resource_id = json.dumps({
                "PlatformApplicationArn": arn_prod,
                "PlatformApplicationArnSandbox": arn_sandbox,
            })

        feedback_attrs = {}
        if props.get("SuccessFeedbackRoleArn"):
            feedback_attrs["SuccessFeedbackRoleArn"] = props["SuccessFeedbackRoleArn"]
        if props.get("FailureFeedbackRoleArn"):
            feedback_attrs["FailureFeedbackRoleArn"] = props["FailureFeedbackRoleArn"]
        if props.get("SuccessFeedbackSampleRate") is not None:
            feedback_attrs["SuccessFeedbackSampleRate"] = str(props["SuccessFeedbackSampleRate"])
        if feedback_attrs:
            for arn in (arn_prod, arn_sandbox):
                if arn:
                    sns.set_platform_application_attributes(
                        PlatformApplicationArn=arn,
                        Attributes=feedback_attrs,
                    )

        data = {"PlatformApplicationArn": arn_prod, "PlatformApplicationArnSandbox": arn_sandbox}
        return {"PhysicalResourceId": physical_resource_id, "Data": data}

    # Create: fetch credentials and create both platform applications
    secret_arn = props["SecretArn"]
    sandbox_secret_arn = props.get("SecretArnSandbox") or secret_arn
    name = props.get("Name", "factchecker-ios-apns")

    def make_create_attrs(creds):
        platform_credential = creds.get("PlatformCredential")
        platform_principal = creds.get("PlatformPrincipal")
        team_id = creds.get("ApplePlatformTeamID")
        bundle_id = creds.get("ApplePlatformBundleID")
        if not all([platform_credential, platform_principal, team_id, bundle_id]):
            raise ValueError(
                "Secret must contain: PlatformCredential (.p8 content), PlatformPrincipal (Key ID), "
                "ApplePlatformTeamID, ApplePlatformBundleID"
            )
        attrs = {
            "PlatformCredential": platform_credential,
            "PlatformPrincipal": platform_principal,
            "ApplePlatformTeamID": team_id,
            "ApplePlatformBundleID": bundle_id,
        }
        if props.get("SuccessFeedbackRoleArn"):
            attrs["SuccessFeedbackRoleArn"] = props["SuccessFeedbackRoleArn"]
        if props.get("FailureFeedbackRoleArn"):
            attrs["FailureFeedbackRoleArn"] = props["FailureFeedbackRoleArn"]
        if props.get("SuccessFeedbackSampleRate") is not None:
            attrs["SuccessFeedbackSampleRate"] = str(props["SuccessFeedbackSampleRate"])
        return attrs

    secret_value = sm.get_secret_value(SecretId=secret_arn)
    creds_prod = json.loads(secret_value["SecretString"])
    create_attrs_prod = make_create_attrs(creds_prod)

    secret_value_sandbox = sm.get_secret_value(SecretId=sandbox_secret_arn)
    creds_sandbox = json.loads(secret_value_sandbox["SecretString"])
    create_attrs_sandbox = make_create_attrs(creds_sandbox)

    resp_prod = sns.create_platform_application(
        Name=name,
        Platform="APNS",
        Attributes=create_attrs_prod,
    )
    arn_prod = resp_prod["PlatformApplicationArn"]

    resp_sandbox = sns.create_platform_application(
        Name=f"{name}-sandbox",
        Platform="APNS_SANDBOX",
        Attributes=create_attrs_sandbox,
    )
    arn_sandbox = resp_sandbox["PlatformApplicationArn"]

    physical_id = json.dumps({
        "PlatformApplicationArn": arn_prod,
        "PlatformApplicationArnSandbox": arn_sandbox,
    })
    return {
        "PhysicalResourceId": physical_id,
        "Data": {
            "PlatformApplicationArn": arn_prod,
            "PlatformApplicationArnSandbox": arn_sandbox,
        },
    }
