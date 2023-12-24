# Pumpkin-Topic
- 슬랙 워크스페이스 내에서 관심사가 같은 사람들과 익명으로 대화를 나눠봐요!
## 권한
- AmazonDynamoDBFullAccess
  - 회원 정보와 채팅 정보를 관리하는 DynamoDB 에 접근하기 위함
- AWSLambda_FullAccess
  - GPT에 대한 요청이 시간이 걸리는 경우 람다 함수의 수행시간 제한이 지나도 새로운 람다 함수가 수행되도록 하기 위함
## 계층
- openai
- slack_bolt
