#!/bin/bash
# Script to view deployed API components

set -e

echo "=== FactChecker API Components ==="
echo ""

# Get the stack name (assuming default naming)
STACK_NAME="ApiStack"
REGION="${AWS_REGION:-us-east-1}"

echo "1. API Endpoint (Load Balancer DNS):"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text 2>/dev/null || echo "  (Output not found - may need to redeploy with outputs)"

echo ""
echo "2. Health Check Endpoint:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiHealthCheck`].OutputValue' \
  --output text 2>/dev/null || echo "  (Output not found - may need to redeploy with outputs)"

echo ""
echo "3. Load Balancer Details:"
LB_ARN=$(aws cloudformation describe-stack-resources \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'StackResources[?ResourceType==`AWS::ElasticLoadBalancingV2::LoadBalancer`].PhysicalResourceId' \
  --output text 2>/dev/null | head -1)

if [ -n "$LB_ARN" ]; then
  echo "  Load Balancer ARN: $LB_ARN"
  LB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns "$LB_ARN" \
    --region "$REGION" \
    --query 'LoadBalancers[0].DNSName' \
    --output text 2>/dev/null)
  echo "  Load Balancer DNS: $LB_DNS"
  echo "  API URL: http://$LB_DNS"
else
  echo "  (Load balancer not found)"
fi

echo ""
echo "4. ECS Service Status:"
CLUSTER_NAME=$(aws cloudformation describe-stack-resources \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'StackResources[?ResourceType==`AWS::ECS::Service`].PhysicalResourceId' \
  --output text 2>/dev/null | cut -d'/' -f2 | head -1)

if [ -n "$CLUSTER_NAME" ]; then
  SERVICE_NAME=$(aws cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'StackResources[?ResourceType==`AWS::ECS::Service`].PhysicalResourceId' \
    --output text 2>/dev/null | cut -d'/' -f3 | head -1)
  
  if [ -n "$SERVICE_NAME" ]; then
    CLUSTER_FULL=$(aws cloudformation describe-stack-resources \
      --stack-name "$STACK_NAME" \
      --region "$REGION" \
      --query 'StackResources[?ResourceType==`AWS::ECS::Service`].PhysicalResourceId' \
      --output text 2>/dev/null | head -1 | cut -d'/' -f1-2)
    
    echo "  Cluster: $CLUSTER_FULL"
    echo "  Service: $SERVICE_NAME"
    
    aws ecs describe-services \
      --cluster "$CLUSTER_FULL" \
      --services "$SERVICE_NAME" \
      --region "$REGION" \
      --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,TaskDefinition:taskDefinition}' \
      --output table 2>/dev/null || echo "  (Could not fetch service status)"
  fi
fi

echo ""
echo "5. Test API Health Endpoint:"
if [ -n "$LB_DNS" ]; then
  echo "  Testing: http://$LB_DNS/health"
  curl -s -o /dev/null -w "  Status: %{http_code}\n" "http://$LB_DNS/health" || echo "  (Could not reach endpoint - service may still be starting)"
else
  echo "  (Load balancer DNS not available)"
fi

echo ""
echo "=== Quick Access Commands ==="
echo ""
echo "Get API endpoint:"
echo "  aws cloudformation describe-stacks --stack-name ApiStack --query 'Stacks[0].Outputs[?OutputKey==\`ApiEndpoint\`].OutputValue' --output text"
echo ""
echo "Test health endpoint:"
if [ -n "$LB_DNS" ]; then
  echo "  curl http://$LB_DNS/health"
else
  echo "  curl http://<LOAD_BALANCER_DNS>/health"
fi
echo ""
echo "View in AWS Console:"
echo "  ECS: https://console.aws.amazon.com/ecs/v2/clusters"
echo "  Load Balancer: https://console.aws.amazon.com/ec2/v2/home#LoadBalancers:"
echo "  CloudFormation: https://console.aws.amazon.com/cloudformation/home#/stacks"

