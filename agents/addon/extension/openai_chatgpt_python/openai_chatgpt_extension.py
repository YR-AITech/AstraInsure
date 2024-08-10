#
#
# Agora Real Time Engagement
# Created by Wei Hu in 2024-05.
# Copyright (c) 2024 Agora IO. All rights reserved.
#
#
from .openai_chatgpt import OpenAIChatGPT, OpenAIChatGPTConfig
from datetime import datetime
from threading import Thread
from rte import (
    Addon,
    Extension,
    register_addon_as_extension,
    RteEnv,
    Cmd,
    Data,
    StatusCode,
    CmdResult,
    MetadataInfo,
)
from .log import logger


CMD_IN_FLUSH = "flush"
CMD_OUT_FLUSH = "flush"
DATA_IN_TEXT_DATA_PROPERTY_TEXT = "text"
DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL = "is_final"
DATA_OUT_TEXT_DATA_PROPERTY_TEXT = "text"
DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT = "end_of_segment"

PROPERTY_BASE_URL = "base_url"  # Optional
PROPERTY_API_KEY = "api_key"  # Required
PROPERTY_MODEL = "model"  # Optional
PROPERTY_PROMPT = "prompt"  # Optional
PROPERTY_FREQUENCY_PENALTY = "frequency_penalty"  # Optional
PROPERTY_PRESENCE_PENALTY = "presence_penalty"  # Optional
PROPERTY_TEMPERATURE = "temperature"  # Optional
PROPERTY_TOP_P = "top_p"  # Optional
PROPERTY_MAX_TOKENS = "max_tokens"  # Optional
PROPERTY_GREETING = "greeting"  # Optional
PROPERTY_PROXY_URL = "proxy_url"  # Optional
PROPERTY_MAX_MEMORY_LENGTH = "max_memory_length"  # Optional

MAX_NODE = 2
BASE_PROMPTS_CHAT = """
# 人物: 王女士

## 描述：

### 基本信息：
- 年龄：36
- 性别：女
- 职业：教师
- 收入水平：中等
- 居住地：上海

### 家庭情况：
- 婚姻状态：已婚
- 配偶年龄：36
- 子女信息：两个孩子，一个10岁，一个6岁
- 家庭成员健康状况：均健康

### 健康状况：
- 当前健康状况：良好
- 医疗历史：无重大疾病史

### 经济状况：
- 经济状况：中等
- 支出优先级：优先孩子

### 保险意识：
- 保险意识：较好
- 保险经历：购买过保险产品
- 保险认知：略微了解保险流程

### 性格：
- 性格类型：平和

### 生活方式：
- 生活习惯：
- 兴趣爱好：

### 情绪和社交：
- 当前情绪：因为最近事务多比较心烦；邻居的孩子生病花费了很多钱，担心自己孩子和丈夫未来生病的情况。
- 未来期望：重视孩子的健康和教育，重视家庭成员的健康。
- 家庭关系：孩子课业有困难，最近经常辅导；丈夫因为工作忙，经常不回家。
- 社会关系：和邻居闹了矛盾

## 任务
作为购买保险的潜在客户王女士，和保险公司销售代理人进行对话，基于人物描述和从销售取得的信息进行交流，目前的对话主要围绕：
- {conditions}

## 规则：
- 作为王女士，必须以符合人物描述中的信息内容进行交流；
- 必须使用中文，说话方式口语化、生活化，语气符合人物描述；
"""
NODE_PROMPTS_CHAT = ["和对方初次接触和了解", "和对方初步交流近期的状况，适当流露相应的情感和信息"]


BASE_PROMPTS_EVAL = """
                    ## 需求
                    请基于潜在客户同保险销售代理人的历史对话进行客观评估，判断其是否满足：
                    - {conditions}
                    
                    评分范围为0-100分，若满足要求，请给出至少70以上的得分；
                    仅返回整数形式得分，不带标点或字符串，如75
                    """
BASE_PROMPTS_FAIL_EVAL = """
                    ## 需求
                    请基于潜在客户同保险销售代理人的历史对话进行客观评估，给出其不满足下述需求的简短理由：
                    - {conditions}

                    不超过100字。
                    """

NODE_PROMPTS_EVAL = ["保险销售代理人需要完成同顾客的初次接触和关系建立", 
                "保险销售代理需要和顾客进行情感上的交流并引导产生情感共鸣"
                    ]


def get_current_time():
    # Get the current time
    start_time = datetime.now()
    # Get the number of microseconds since the Unix epoch
    unix_microseconds = int(start_time.timestamp() * 1_000_000)
    return unix_microseconds


def is_punctuation(char):
    if char in [",", "，", ".", "。", "?", "？", "!", "！"]:
        return True
    return False


def parse_sentence(sentence, content):
    remain = ""
    found_punc = False

    for char in content:
        if not found_punc:
            sentence += char
        else:
            remain += char

        if not found_punc and is_punctuation(char):
            found_punc = True

    return sentence, remain, found_punc


class OpenAIChatGPTExtension(Extension):
    memory = []
    chat_count = 0
    max_memory_length = 10
    outdate_ts = 0
    openai_chatgpt = None
    openai_chatgpt_eval = None

    def on_start(self, rte: RteEnv) -> None:
        logger.info("OpenAIChatGPTExtension on_start")
        # Prepare configuration
        openai_chatgpt_config = OpenAIChatGPTConfig.default_config()

        try:
            base_url = rte.get_property_string(PROPERTY_BASE_URL)
            if base_url:
                openai_chatgpt_config.base_url = base_url
        except Exception as err:
            logger.info(f"GetProperty required {PROPERTY_BASE_URL} failed, err: {err}")

        try:
            api_key = rte.get_property_string(PROPERTY_API_KEY)
            openai_chatgpt_config.api_key = api_key
        except Exception as err:
            logger.info(f"GetProperty required {PROPERTY_API_KEY} failed, err: {err}")
            return

        try:
            model = rte.get_property_string(PROPERTY_MODEL)
            if model:
                openai_chatgpt_config.model = model
        except Exception as err:
            logger.info(f"GetProperty optional {PROPERTY_MODEL} error: {err}")

        try:
            prompt = rte.get_property_string(PROPERTY_PROMPT)
            if prompt:
                openai_chatgpt_config.prompt = prompt
        except Exception as err:
            logger.info(f"GetProperty optional {PROPERTY_PROMPT} error: {err}")

        try:
            frequency_penalty = rte.get_property_float(PROPERTY_FREQUENCY_PENALTY)
            openai_chatgpt_config.frequency_penalty = float(frequency_penalty)
        except Exception as err:
            logger.info(
                f"GetProperty optional {PROPERTY_FREQUENCY_PENALTY} failed, err: {err}"
            )

        try:
            presence_penalty = rte.get_property_float(PROPERTY_PRESENCE_PENALTY)
            openai_chatgpt_config.presence_penalty = float(presence_penalty)
        except Exception as err:
            logger.info(
                f"GetProperty optional {PROPERTY_PRESENCE_PENALTY} failed, err: {err}"
            )

        try:
            temperature = rte.get_property_float(PROPERTY_TEMPERATURE)
            openai_chatgpt_config.temperature = float(temperature)
        except Exception as err:
            logger.info(
                f"GetProperty optional {PROPERTY_TEMPERATURE} failed, err: {err}"
            )

        try:
            top_p = rte.get_property_float(PROPERTY_TOP_P)
            openai_chatgpt_config.top_p = float(top_p)
        except Exception as err:
            logger.info(f"GetProperty optional {PROPERTY_TOP_P} failed, err: {err}")

        try:
            max_tokens = rte.get_property_int(PROPERTY_MAX_TOKENS)
            if max_tokens > 0:
                openai_chatgpt_config.max_tokens = int(max_tokens)
        except Exception as err:
            logger.info(
                f"GetProperty optional {PROPERTY_MAX_TOKENS} failed, err: {err}"
            )

        try:
            proxy_url = rte.get_property_string(PROPERTY_PROXY_URL)
            openai_chatgpt_config.proxy_url = proxy_url
        except Exception as err:
            logger.info(f"GetProperty optional {PROPERTY_PROXY_URL} failed, err: {err}")

        try:
            greeting = rte.get_property_string(PROPERTY_GREETING)
        except Exception as err:
            logger.info(f"GetProperty optional {PROPERTY_GREETING} failed, err: {err}")

        try:
            prop_max_memory_length = rte.get_property_int(PROPERTY_MAX_MEMORY_LENGTH)
            if prop_max_memory_length > 0:
                self.max_memory_length = int(prop_max_memory_length)
        except Exception as err:
            logger.info(
                f"GetProperty optional {PROPERTY_MAX_MEMORY_LENGTH} failed, err: {err}"
            )


        # Create openaiChatGPT instance
        try:
            self.openai_chatgpt = OpenAIChatGPT(openai_chatgpt_config)
            logger.info(
                f"newOpenaiChatGPT succeed with max_tokens: {openai_chatgpt_config.max_tokens}, model: {openai_chatgpt_config.model}"
            )
        except Exception as err:
            logger.info(f"newOpenaiChatGPT failed, err: {err}")

        # Create GPT instance for evaluation
        try:
            self.openai_chatgpt_eval = OpenAIChatGPT(openai_chatgpt_config)
            logger.info(
                f"newOpenaiChatGPT for eval succeed with max_tokens: {openai_chatgpt_eval_config.max_tokens}, model: {openai_chatgpt_eval_config.model}"
            )
        except Exception as err:
            logger.info(f"newOpenaiChatGPT for eval failed, err: {err}")

        # Send greeting if available
        if greeting:
            try:
                output_data = Data.create("text_data")
                output_data.set_property_string(
                    DATA_OUT_TEXT_DATA_PROPERTY_TEXT, greeting
                )
                output_data.set_property_bool(
                    DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, True
                )
                rte.send_data(output_data)
                logger.info(f"greeting [{greeting}] sent")
            except Exception as err:
                logger.info(f"greeting [{greeting}] send failed, err: {err}")
        rte.on_start_done()

    def on_stop(self, rte: RteEnv) -> None:
        logger.info("OpenAIChatGPTExtension on_stop")
        rte.on_stop_done()

    def on_cmd(self, rte: RteEnv, cmd: Cmd) -> None:
        logger.info("OpenAIChatGPTExtension on_cmd")
        cmd_json = cmd.to_json()
        logger.info("OpenAIChatGPTExtension on_cmd json: " + cmd_json)

        cmd_name = cmd.get_name()

        if cmd_name == CMD_IN_FLUSH:
            self.outdate_ts = get_current_time()
            cmd_out = Cmd.create(CMD_OUT_FLUSH)
            rte.send_cmd(cmd_out, None)
            logger.info(f"OpenAIChatGPTExtension on_cmd sent flush")
        else:
            logger.info(f"OpenAIChatGPTExtension on_cmd unknown cmd: {cmd_name}")
            cmd_result = CmdResult.create(StatusCode.ERROR)
            cmd_result.set_property_string("detail", "unknown cmd")
            rte.return_result(cmd_result, cmd)
            return

        cmd_result = CmdResult.create(StatusCode.OK)
        cmd_result.set_property_string("detail", "success")
        rte.return_result(cmd_result, cmd)

    def on_data(self, rte: RteEnv, data: Data) -> None:
        """
        on_data receives data from rte graph.
        current supported data:
          - name: text_data
            example:
            {name: text_data, properties: {text: "hello"}
        """
        logger.info(f"OpenAIChatGPTExtension on_data")

        def chat_quality_evaluation(memory, node):
            self.openai_chatgpt_eval.config.prompt = BASE_PROMPTS_EVAL.format(conditions=NODE_PROMPTS_EVAL[node-1])
            try: 
                logger.info(
                f"GetEval for node: [{node}] memory: {memory}"
            )
                resp = self.openai_chatgpt_eval.get_chat_completion(memory) 
                return resp
            except Exception as err:
                logger.info(
                f"GetEval for node: [{node}] failed, err: {err}"
            )
                return 


        # Assume 'data' is an object from which we can get properties
        try:
            is_final = data.get_property_bool(DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL)
            if not is_final:
                logger.info("ignore non-final input")
                return
        except Exception as err:
            logger.info(
                f"OnData GetProperty {DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL} failed, err: {err}"
            )
            return

        # Get input text
        try:
            input_text = data.get_property_string(DATA_IN_TEXT_DATA_PROPERTY_TEXT)
            if not input_text:
                logger.info("ignore empty text")
                return
            logger.info(f"OnData input text: [{input_text}]")
        except Exception as err:
            logger.info(
                f"OnData GetProperty {DATA_IN_TEXT_DATA_PROPERTY_TEXT} failed, err: {err}"
            )
            return


        # Prepare memory
        if len(self.memory) > self.max_memory_length:
            self.memory.pop(0)
        self.memory.append({"role": "user", "content": input_text})


        def chat_completions_stream_worker(chatgpt, start_time, input_text, memory, chat_count):
            try:
                logger.info(
                    f"GetChatCompletionsStream for input text: [{input_text}] memory: {memory}"
                )

                # Get result from AI
                resp = chatgpt.get_chat_completions_stream(memory)
                if resp is None:
                    logger.info(
                        f"GetChatCompletionsStream for input text: [{input_text}] failed"
                    )
                    return

                sentence = ""
                full_content = ""
                first_sentence_sent = False

                for chat_completions in resp:
                    if start_time < self.outdate_ts:
                        logger.info(
                            f"GetChatCompletionsStream recv interrupt and flushing for input text: [{input_text}], startTs: {start_time}, outdateTs: {self.outdate_ts}"
                        )
                        break

                    if (
                        len(chat_completions.choices) > 0
                        and chat_completions.choices[0].delta.content is not None
                    ):
                        content = chat_completions.choices[0].delta.content
                    else:
                        content = ""

                    full_content += content

                    while True:
                        sentence, content, sentence_is_final = parse_sentence(
                            sentence, content
                        )
                        if len(sentence) == 0 or not sentence_is_final:
                            logger.info(f"sentence {sentence} is empty or not final")
                            break
                        logger.info(
                            f"GetChatCompletionsStream recv for input text: [{input_text}] got sentence: [{sentence}]"
                        )

                        # send sentence
                        try:
                            output_data = Data.create("text_data")
                            output_data.set_property_string(
                                DATA_OUT_TEXT_DATA_PROPERTY_TEXT, sentence
                            )
                            output_data.set_property_bool(
                                DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, False
                            )
                            rte.send_data(output_data)
                            logger.info(
                                f"GetChatCompletionsStream recv for input text: [{input_text}] sent sentence [{sentence}]"
                            )
                        except Exception as err:
                            logger.info(
                                f"GetChatCompletionsStream recv for input text: [{input_text}] send sentence [{sentence}] failed, err: {err}"
                            )
                            break

                        sentence = ""
                        if not first_sentence_sent:
                            first_sentence_sent = True
                            logger.info(
                                f"GetChatCompletionsStream recv for input text: [{input_text}] first sentence sent, first_sentence_latency {get_current_time() - start_time}ms"
                            )

                # remember response as assistant content in memory
                memory.append({"role": "assistant", "content": full_content})
                chat_count += 1

                # send end of segment
                try:
                    output_data = Data.create("text_data")
                    output_data.set_property_string(
                        DATA_OUT_TEXT_DATA_PROPERTY_TEXT, sentence
                    )
                    output_data.set_property_bool(
                        DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, True
                    )
                    rte.send_data(output_data)
                    logger.info(
                        f"GetChatCompletionsStream for input text: [{input_text}] end of segment with sentence [{sentence}] sent"
                    )
                except Exception as err:
                    logger.info(
                        f"GetChatCompletionsStream for input text: [{input_text}] end of segment with sentence [{sentence}] send failed, err: {err}"
                    )
                    

            except Exception as e:
                logger.info(
                    f"GetChatCompletionsStream for input text: [{input_text}] failed, err: {e}"
                )

        def chat(start_time, input_text, memory, chat_count):
            if chat_count == 0:
                self.openai_chatgpt.config.prompt = BASE_PROMPTS_CHAT.format(conditions=NODE_PROMPTS_CHAT[0])
            if chat_count == 0 or chat_count % 5 != 0:
                chat_completions_stream_worker(self.openai_chatgpt, start_time, input_text, memory, chat_count)

            else:
                node = chat_count / 5
                node_prompt_eval = BASE_PROMPTS_EVAL.format(conditions=NODE_PROMPTS_EVAL[node-1])
                self.openai_chatgpt_eval.config.prompt = node_prompt_eval
                resp = chat_quality_evaluation(memory, node)
                score = resp.["choices"][0]["message"]["content"]

                try:
                    score = int(score)
                    logger.info(
                        f"GetEvalScore : {score} of node {node}"
                    )

                except Exception as err:
                    logger.info(
                        f"GetEvalScore : {score} of node {node} failed, err: {err}"
                    )
                    score = 70

            if score >= 70:

                if node == MAX_NODE:
                    ############TODO: 弹窗提示交易成功
                    chat_count = 0
                    memory = []
                    #self.openai_chatgpt.config.prompt = BASE_PROMPTS_CHAT.format(conditions=NODE_PROMPTS_CHAT[0])
                    #self.openai_chatgpt_eval.config.prompt = BASE_PROMPTS_EVAL.format(conditions=NODE_PROMPTS_EVAL[0])


                else:
                    self.openai_chatgpt.config.prompt = BASE_PROMPTS_CHAT.format(conditions=NODE_PROMPTS_CHAT[node])
                    chat_completions_stream_worker(start_time, input_text, memory, chat_count)

            else:
                self.openai_chatgpt_eval.config.prompt = BASE_PROMPTS_FAIL_EVAL.format(conditions=NODE_PROMPTS_EVAL[node-1])
                chat_completions_stream_worker(self.openai_chatgpt_eval, start_time, input_text, memory, chat_count)
                #############TODO: 弹窗提示交易失败
                chat_count = 0
                memory = []

        # Start thread to request and read responses from OpenAI
        start_time = get_current_time()
        thread = Thread(
            target=chat,
            args=(start_time, input_text, self.memory, self.chat_count),
        )
        thread.start()
        logger.info(f"OpenAIChatGPTExtension on_data end")

@register_addon_as_extension("openai_chatgpt_python")
class OpenAIChatGPTExtensionAddon(Addon):
    def on_create_instance(self, rte: RteEnv, addon_name: str, context) -> None:
        logger.info("on_create_instance")
        rte.on_create_instance_done(OpenAIChatGPTExtension(addon_name), context)
