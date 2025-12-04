class TextLineBreak:
    """
    Text Line Break
    功能：
    1. 将输入文本按指定字符数换行。
    2. 智能识别中英文单词边界。
    3. 【避头规则终极版】防止标点出现在行首：
       - 优先将标点挤入上一行（延展）。
       - 如果无法延展，回溯换行时也会避开标点前的位置。
    """
    
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "forceInput": True}),
                "max_chars_per_line": ("INT", {"default": 50, "min": 1, "max": 10000, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("formatted_text",)
    FUNCTION = "process"
    
    CATEGORY = "Element_easy/Text"

    def process(self, text, max_chars_per_line):
        if not text:
            return ("",)

        lines = text.split('\n')
        result_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                result_lines.append("")
                continue
                
            if len(line) <= max_chars_per_line:
                result_lines.append(line)
            else:
                result_lines.append(self.wrap_single_paragraph(line, max_chars_per_line))

        return ("\n".join(result_lines),)

    def wrap_single_paragraph(self, text, width):
        if width <= 0: return text
        wrapped_output = []
        
        # 避头字符集
        # 包含了全角/半角标点
        no_start_chars = "，。？！：；”’）》]…,.;:?!)]}、"
        
        while len(text) > 0:
            # 如果剩余文本比宽度短，直接结束
            if len(text) <= width:
                wrapped_output.append(text)
                break
                
            split_at = width
            
            # --- 策略1: 延展 (Extension) ---
            # 如果当前切分点（下一行首字符）是避头字符，尝试把它“挤”进当前行
            while split_at < len(text) and text[split_at] in no_start_chars:
                split_at += 1
            
            # 标记是否发生了延展
            is_extended = (split_at > width)
            
            # --- 策略2: 回溯 (Backtracking) ---
            # 只有在没有发生延展的情况下（说明当前切分点很普通），才尝试往回找更完美的单词断点
            if not is_extended:
                found_safe_break = False
                
                # 从 width 往回找
                for i in range(split_at, 0, -1):
                    char_before = text[i-1]
                    char_after = text[i] # 这就是下一行的第一个字
                    
                    # A. 判断这里是否适合断开 (保护单词完整性)
                    # 1. 空格是天然断点
                    is_space_break = (char_before == ' ')
                    # 2. 非ASCII字符（中文/全角符号等）通常都可以断，只要不是断在英文单词中间
                    is_cjk_break = (ord(char_before) > 127)
                    
                    is_valid_break_point = (is_space_break or is_cjk_break)
                    
                    if not is_valid_break_point:
                        continue

                    # B. 判断断开后是否违反避头规则
                    # 如果我们在 'i' 处断开，那么 'char_after' 就会变成下一行的行首
                    # 如果它是避头字符不能断！
                    if char_after in no_start_chars:
                        continue
                        
                    # 找到了既不破坏单词，又不会导致下一行标点抬头的完美切分点
                    split_at = i
                    found_safe_break = True
                    break
                
                # 如果回溯到底都没找到（比如一整行超长英文无空格），那就只能在 width 处硬切
                if not found_safe_break:
                    split_at = width

            # --- 执行切分 ---
            line_part = text[:split_at]
            
            if line_part.endswith(' '):
                line_part = line_part[:-1]
                
            wrapped_output.append(line_part)
            
            text = text[split_at:]
            text = text.lstrip()
            
        return "\n".join(wrapped_output)
