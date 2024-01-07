import json
import logging
import os
import boto3
import random
import threading
import openai
from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler
from boto3.dynamodb.conditions import Key

BOT_TOKEN = os.environ['PROD_BOT_TOKEN']
API_KEY = os.environ['PROD_GPT_API_KEY']
SIGNING_SECRET = os.environ['PROD_SIGNING_SECRET']

app = App(
    token=BOT_TOKEN,
    signing_secret=SIGNING_SECRET,
    process_before_response=True
)

dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
dbtable = dynamodb.Table('inha-pumpkin-coach')
handler = SlackRequestHandler(app)
SlackRequestHandler.clear_all_log_handlers()
logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)
logger = logging.getLogger()

def random_name_generator():
    PK = 'namespace'
    SK = 'namespace'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK)) # 이름 데이터베이스 조회
    adjectives = response['Items'][0]['adjectives']
    adjective = adjectives[random.randrange(0,len(adjectives))]
    nouns = response['Items'][0]['nouns']
    noun = nouns[random.randrange(0,len(nouns))]
    name = adjective + ' ' + noun + ' ' + str(random.randrange(1,1001))
    return name

def respond_to_slack_within_3_seconds(ack):
    ack()


def chatgpt_response(message, say):
    
    # OpenAI API 키를 설정합니다
    openai.api_key = API_KEY
    
    # OpenAI GPT-3를 사용하여 텍스트를 생성합니다
    response = openai.Completion.create(
        engine='text-davinci-003',
        prompt=message['text'][5:],
        temperature=0.5,
        max_tokens=1024,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    
    say("답변: " + str(response['choices'][0]['text']))

app.message("!GPT")(
    ack=respond_to_slack_within_3_seconds,
    lazy=[chatgpt_response]
)

@app.message("!등록")
def register(message, say):
    if message["text"] != '!등록':
        message_receive(message, say)
        return
    team = message['team']
    user = message['user']
    channel = message['channel']
    PK = f'topic#{team}'
    SK = f'user#{user}'
    dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'channel': {'Value':channel, 'Action':'PUT'},'topic': {'Value': '', 'Action':'PUT'}, 'nickName': {'Value': '', 'Action': 'PUT'}}) # 주제채팅 사용자 데이터 수정
    say(
        {
            "blocks": [
        		{
        			"type": "header",
        			"text": {
        				"type": "plain_text",
        				"text": '주제채팅방에 사용자 정보가 등록되었습니다.'
        			}
        		}
    		]
		}
    )
    return

@app.message("!도움") # 도움말 출력
def print_help(message, say):
    if message["text"] != '!도움':
        message_receive(message, say)
        return
    say(
        {
        	"blocks": [
        		{
        			"type": "header",
        			"text": {
        				"type": "plain_text",
        				"text": ":jack_o_lantern: Pumpkin-Topic :bulb: 도움말"
        			}
        		},
        		{
        			"type": "divider"
        		},
        		{
        			"type": "context",
        			"elements": [
        				{
        					"type": "mrkdwn",
        					"text": "*!등록* 주제채팅을 시작하기 위해 사용자를 등록합니다. (:exclamation:서비스 이용을 위해 필수:exclamation:)\n*!목록* 진행중인 주제의 목록을 보여줍니다.\n*!입장 (주제 이름)* 주제 채팅에 입장합니다.\n*!만들기 (주제 이름)* 주제 채팅을 만들고 입장합니다.\n*!GPT (스크립트)* GPT에게 질문합니다\n*!나가기* 채팅방에 존재했다면 채팅방에서 나갑니다.\n*!도움* Pumpkin-Topic의 도움말을 보여줍니다.\n"
        				}
        			]
        		}
        	]
        }
    )
    return

@app.message("!나가기") # 채팅방 나가기
def message_exit(message, say, client):
    if message["text"] != '!나가기': # 커멘드와 정확히 일치하지 않으면 일반 메세지로 인식
        message_receive(message, say)
        return
    team = message['team']
    user = message['user']
    channel = message['channel']
    PK = f'topic#{team}'
    SK = f'user#{user}'
    
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK)) # 주제채팅 사용자 데이터 조회
    topic = response['Items'][0]['topic'] # 주제채팅 사용자가 속한 주제채팅 조회
    nickName = response['Items'][0]['nickName']
    if topic == '': # 소속한 주제채팅이 존재하지 않는 경우
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": '현재 채팅방에 존재하지 않습니다.'
            			}
            		}
        		]
    		}
        )
        return
    
    # 데이터베이스에서 사용자 nickName 제거, topic 제거
    dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'topic': {'Value': '', 'Action':'PUT'}, 'nickName': {'Value': '', 'Action': 'PUT'}}) # 주제채팅 사용자 데이터 수정
    SK = f'group#{topic}' # 주제채팅 그룹 sort key
    
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK)) # 주제채팅 그룹 데이터 조회
    channels = response['Items'][0]['channels'] # 주제채팅 그룹 내 속한 사용자들의 채널 id 조회
    publish_message(channels, f'{nickName} 님이 채팅방에 나갔습니다.', say)
    
    # 주제채팅방에서 channel_id 제거
    if len(response['Items'][0]['channels']) <= 1: # 주제 채팅방에 남아있는 사람이 없는 경우
        response = dbtable.delete_item(Key={'PK':PK,'SK':SK})
    else: # 주제 채팅방에 남아 있는 사람이 있는 경우
        channels.remove(channel)
        response = dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'channels': {'Value': channels, 'Action': 'PUT'}})
    
    client.conversations_setTopic(token=bot_token,channel=channel,topic='속한 채팅방 없음. 대화를 시작해보세요!')
    say(
        {
            "blocks": [
        		{
        			"type": "header",
        			"text": {
        				"type": "plain_text",
        				"text": f'{topic} 주제채팅방을 나갑니다.'
        			}
        		}
    		]
		}
    )
    return
        
@app.message("!입장 ") # 주제 입장
def enter_topic(message, say, client):
    if  message['text'].split()[0] != '!입장' or len(message["text"].split()) != 2:
        message_receive(message, say)
        return
    team = message['team']
    user = message['user']
    channel = message['channel']
    topic = message['text'].split()[1]
    PK = f'topic#{team}'
    
    # 사용자가 현재 주제채팅에 존재한다면 이동못하도록 제지
    SK = f'user#{user}'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK))
    if response['Items'][0]['topic'] != '':
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": f'현재 {response["Items"][0]["topic"]} 주제채팅방에 있어 {topic} 주제채팅방으로 이동할 수 없습니다.\n주제채팅방에서 나간 후 새로운 주제 채팅방으로 이동하세요. (!나가기)'
            			}
            		}
        		]
    		}
        )
        return
    SK = f'group#{topic}'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK)) # 주제채팅 그룹 데이터 조회
    
    if response['Count'] == 0:
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": f'{topic} 주제채팅방은 존재하지 않습니다.'
            			}
            		}
        		]
    		}
        )
        return
    
    # 새로운 그룹에 사용자 주제채팅 채널 등록
    channels = response["Items"][0]['channels']
    channels.append(channel)
    SK = f'group#{topic}'
    response = dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'channels': {'Value': channels, 'Action': 'PUT'}}, ReturnValues='ALL_NEW')
    messages = response['Attributes']['messages']
    
    # 익명 이름 생성, 사용자 nickName, topic 저장 구현
    new_nickName = random_name_generator()
    SK = f'user#{user}'
    response = dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'nickName': {'Value': new_nickName, 'Action': 'PUT'}, 'topic': {'Value': topic, 'Action': 'PUT'}}, ReturnValues='ALL_OLD')
    
    client.conversations_setTopic(token=bot_token,channel=channel,topic=f'{topic} 주제채팅방에 {new_nickName} 으로 참여중')
    
    say(
        {
            "blocks": [
        		{
        			"type": "header",
        			"text": {
        				"type": "plain_text",
        				"text": f'{new_nickName}님, {topic} 주제채팅방에 접속하였습니다.'
        			}
        		},
    		    {
        			"type": "context",
        			"elements": [
        				{
        					"type": "mrkdwn",
        					"text": message_loader(messages)
        				}
        			]
        		}
    		]
            
        }
    )
    publish_message(channels, f'{new_nickName} 님이 채팅방에 참가 하였습니다.', say)
    return
    
def message_loader(messages):
    result = ''
    for key, message in sorted(messages.items()):
        result += message + '\n'
    return result

@app.message("!만들기 ")
def make_topic(message, say, client):
    if message['text'].split()[0] != '!만들기' or len(message['text'].split()) != 2: # '!만들기 (주제이름)' 형식의 입력이 아닌경우 채팅으로 인식
        message_receive(message, say)
        return
    team = message['team']
    user = message['user']
    topic = message['text'].split()[1]
    channel = message['channel']
    PK = f'topic#{team}'
    
    # 사용자가 현재 주제채팅에 존재한다면 이동못하도록 제지
    SK = f'user#{user}'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK))
    if response['Items'][0]['topic'] != '':
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": f'현재 {response["Items"][0]["topic"]}주제채팅방에 있습니다.\n주제채팅방에서 나간 후 새로운 주제 채팅방으로 이동하세요. (!나가기)'
            			}
            		}
        		]
    		}
        )
        return
    
    SK = f'group#{topic}'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK)) # 주제채팅의 그룹 데이터 조회
    
    # 주제채팅의 사용자 데이터 수정
    SK = f'user#{user}'
    new_nickName = random_name_generator()
    dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'nickName': {'Value': new_nickName, 'Action': 'PUT'}, 'topic': {'Value': topic, 'Action': 'PUT'}})
    
    client.conversations_setTopic(token=bot_token,channel=channel,topic=f'{topic} 주제 채팅방 참여중')
    
    if len(response['Items']) != 0: # 해당 주제 채팅이 이미 존재하는 경우
        channels = response['Items'][0]['channels']
        channels.append(channel)
        SK = f'group#{topic}'
        dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'channels': {'Value': channels, 'Action': 'PUT'}})
        
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": f'{new_nickName}님, 이미 존재하는 {topic} 주제채팅방에 접속하였습니다.'
            			}
            		},
        		    {
            			"type": "context",
            			"elements": [
            				{
            					"type": "mrkdwn",
            					"text": message_loader(response['Items'][0]['messages'])
            				}
            			]
            		}
        		]
                
            }
        )
        publish_message(channels, f'{new_nickName} 님이 채팅방에 참가 하였습니다.', say)
        return
    
    # 해당 주제 채팅이 존재하지 않는 경우
    
    # 주제채팅의 그룹 데이터 생성
    channels = list()
    channels.append(channel)
    messages = dict()
    SK = f'group#{topic}'
    dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'channels': {'Value': channels, 'Action': 'PUT'}, 'messages' : {'Value': messages, 'Action': 'PUT'}})
    
    say(
        {
            "blocks": [
        		{
        			"type": "header",
        			"text": {
        				"type": "plain_text",
        				"text": f'{new_nickName}님, 새롭게 생성된 {topic} 주제채팅방에 접속하였습니다.'
        			}
        		}
    		]
		}
	)
    publish_message(channels, f'{new_nickName} 님이 채팅방에 참가 하였습니다.', say)
    return

@app.message("!목록") # 주제 목록 출력
def print_topic(message, say):
    if message["text"] != '!목록':
        message_receive(message, say)
        return
    team_id = message["team"]
    PK = f'topic#{team_id}'
    SK = 'group#'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').begins_with(SK))
    if len(response['Items']) == 0:
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": '채팅방이 존재하지 않습니다.'
            			}
            		}
        		]
    		}
        )
    say(get_topics_format(response["Items"]))
    return

def get_topics_format(items): # 개수 제한 로직 추가 필요
    result = ''
    for item in items:
        result += f'- {item["SK"].split("#")[1]}\n'
    return {
        "blocks" : [
    		{
    			"type": "header",
    			"text": {
    				"type": "plain_text",
    				"text": "진행중인 주제"
    			}
    		},
            {
                "type" : "context",
                "elements" : [
                    {
                        "type" : "mrkdwn",
                        "text" : result
                    }
                ]
            }
        ]
    }
    return
    
@app.message()
def message_receive(message, say):
    print('message : ' + str(message))
    text = message['text']
    team = message['team']
    user = message['user']
    channel = message['channel']
    ts = message['ts']
    
    PK = f'topic#{team}'
    SK = f'user#{user}'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK))
    nickName = response['Items'][0]['nickName']
    topic = response['Items'][0]['topic']
    
    if topic == '':
        say(
            {
                "blocks": [
            		{
            			"type": "header",
            			"text": {
            				"type": "plain_text",
            				"text": '현재 채팅방에 존재하지 않습니다.\n(!도움) 을 입력해 사용방법을 알아보세요.'
            			}
            		}
        		]
    		}
        )
        return
    
    SK = f'group#{topic}'
    response = dbtable.query(Select='ALL_ATTRIBUTES',KeyConditionExpression=Key('PK').eq(PK)&Key('SK').eq(SK))
    channels = response['Items'][0]['channels']
    messages = response['Items'][0]['messages']
    
    channels.remove(channel)
    
    pub_text = f'*{nickName}* {text}'
    messages[ts] = pub_text
    dbtable.update_item(Key={'PK':PK,'SK':SK}, AttributeUpdates={'messages' : {'Value': messages, 'Action': 'PUT'}})
    
    publish_message(channels, pub_text, say)
    return
    
def publish_message(channels, pub_text, say):
    threads = []
    for channel in channels:
        t = threading.Thread(target=send_message, args=(channel,pub_text,say,))
        threads.append(t)
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
        
    return

def send_message(channel, text, say):
    say(text=text,channel=channel)
    return

def lambda_handler(event, context):
	return handler.handle(event, context)
