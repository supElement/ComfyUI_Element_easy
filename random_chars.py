import random
import re

class RandomCharacterGenerator:
    """
    Random Character Generator
    功能：将输入的文本(A-D)用连接符连接，并根据设置的位置添加从“字符池”中随机抽取的字符。
    """
    
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                # 1. 字符池
                "character_pool": ("STRING", {
                    "default": "★☆✡✦✧✩✪✫✬✭✮✯✰✱✲✳✴✵✶✷✸✹✺✻✼✽✾✿❀❁❂❃❄❅❆❇❈❉❊❋✢✣✤✥꙳ᕯ⁂⁎⁑▲▼◀▶◣◢◥◤△▽◁▷⊿∇▴▾◂▸▵▿▹◃●❍○◎⊙◌◯◍◐◑◒◓◔◕◖◗⊕⊖⊗⊘⊚⊛⊜⊝■□▢▣▤▥▦▧▨▩▪▫▬▭▮▯▰▱▓▒░◆◇◈◊❖⟡⎔←↑→↓↔↕↖↗↘↙➔➘➙➚➛➜➝➞➟➠➡➢➣➤➥➦➧➨➩➪➫➬➭➮➯➱➲➳➴➵➶➷➸➹➺➻➼➽➾❤❥❣♡💘💓💔💖💗💙💚💛💜🖤❦❧☙⚘⚜✓✔✕✖✗✘✝✞✟✠✚✜✛☀☁☂☃☄☾☽☼♩♪♫♬♭♮♯♠♣♥♦♔♕♖♗♘♙♚♛♜♝♞♟✂✎✐✈✉☎☏⌛⏳⌚⚛⚙⚓⚖⚡⚠「」『』〖〗【】〔〕︵︶︷︸︹︺︻︼︽︾⌞⌟⌜⌝⌊⌋⌈⌉", 
                    "multiline": True, 
                    "placeholder": "输入随机字符库"
                }),
                # 2. 生成数量
                "max_count": ("INT", {
                    "default": 10, "min": 0, "max": 10000, "step": 1, "display": "number" 
                }),
                # 3. 连接符
                "link_text": ("STRING", {
                    "default": "", "multiline": False, "placeholder": "连接符"
                }),
                # 4. 插入位置
                "location": (["end", "insert", "before"], {"default": "end"}),
                # 5. 种子
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "text_A": ("STRING", {"forceInput": True}),
                "text_B": ("STRING", {"forceInput": True}),
                "text_C": ("STRING", {"forceInput": True}),
                "text_D": ("STRING", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("final_text", "char_count")
    FUNCTION = "process"
    
   
    CATEGORY = "Element_easy/Text"

    def process(self, character_pool, max_count, link_text, location, seed, text_A=None, text_B=None, text_C=None, text_D=None):
        valid_texts = []
        inputs = [text_A, text_B, text_C, text_D]
        for t in inputs:
            if t is not None and t != "":
                valid_texts.append(t)
        
        joined_text = link_text.join(valid_texts)
        
        random.seed(seed)
        count = random.randint(0, max_count)
        
        if not character_pool: 
            character_pool = " " 
            
        char_list = []
        if count > 0:
            char_list = random.choices(character_pool, k=count)
        
        generated_chars = "".join(char_list)
        final_result = ""

        if location == "end":
            final_result = joined_text + generated_chars
            
        elif location == "before":
            final_result = generated_chars + joined_text
            
        elif location == "insert":
            if count == 0:
                final_result = joined_text
            else:
                # 定义标点符号正则 (包含中英文常见标点)
                # 捕获组 () 会在 split 后保留标点符号
                punc_pattern = r'([，。！？；：,.!?;:])'
                parts = re.split(punc_pattern, joined_text)
                
                # 找出哪些部分是标点符号 (在 parts 列表中的索引)
                punc_indices = [i for i, part in enumerate(parts) if re.match(punc_pattern, part)]
                num_slots = len(punc_indices)
                
                if num_slots == 0:
                    # 如果没有检测到标点符号，回退到追加到末尾
                    final_result = joined_text + generated_chars
                else:
                    # 字符分配逻辑：将随机字符列表切片分配给每个标点
                    char_idx = 0
                    chars_per_slot = []
                    
                    remaining_chars = count
                    for i in range(num_slots):
                        remaining_slots = num_slots - i
                        # 计算当前槽位应分配的字符数
                        take = remaining_chars // remaining_slots
                        
                        chunk = "".join(char_list[char_idx : char_idx + take])
                        chars_per_slot.append(chunk)
                        
                        char_idx += take
                        remaining_chars -= take
                    
                    # 将分配好的字符拼接到对应的标点符号后面
                    current_slot = 0
                    for idx in punc_indices:
                        parts[idx] = parts[idx] + chars_per_slot[current_slot]
                        current_slot += 1
                    
                    final_result = "".join(parts)

        return (final_result, count)
