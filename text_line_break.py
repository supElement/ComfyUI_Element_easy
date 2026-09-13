import unicodedata


class TextLineBreak:
    """
    InDesign 风格的中英文混排换行节点

    1. 按视觉宽度断行：全角=1字宽，半角=0.5字宽。
    2. 完整避头尾 + 标点压缩 / 标点悬挂。
    3. 半角补齐（pad_odd_halfwidth）：半角字符数为奇数的行补一个空格（单词感知，
       不在已有空格旁重复插空格）。
    4. 保留段首缩进：缩进只影响第一行宽度，续行按全宽断行，
       所有行的右边缘一致。
    """

    NO_START = "，。、；：？！）》〉】」』”’…％‰·.,;:?!)]}>%"
    NO_END = "（《〈【「『“‘([{"
    FORCE_WIDE = set("“”‘’—–…·")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "forceInput": True}),
                "max_chars_per_line": ("INT", {"default": 50, "min": 1, "max": 10000, "step": 1}),
            },
            "optional": {
                "punctuation_squeeze": ("BOOLEAN", {"default": True}),
                "hanging_punctuation": ("BOOLEAN", {"default": True}),
                "pad_odd_halfwidth": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("formatted_text",)
    FUNCTION = "process"
    CATEGORY = "Element_easy/Text"

    # ---------------- 基础判定 ----------------

    @classmethod
    def _cw(cls, ch):
        """半宽单位：全角=2，半角=1"""
        if ch in cls.FORCE_WIDE:
            return 2
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            return 2
        return 1

    @classmethod
    def _hw(cls, ch):
        return cls._cw(ch) == 1

    @classmethod
    def _word_char(cls, ch):
        return ch.isascii() and (ch.isalnum() or ch in "-_+/@#&=")

    @classmethod
    def _is_no_start(cls, tok):
        return len(tok) == 1 and tok in cls.NO_START

    @classmethod
    def _is_no_end(cls, tok):
        return len(tok) == 1 and tok in cls.NO_END

    @classmethod
    def _tw(cls, tok):
        return sum(cls._cw(c) for c in tok)

    # ---------------- 分词 ----------------

    @classmethod
    def _tokenize(cls, text):
        tokens, buf = [], ""

        def flush():
            nonlocal buf
            if buf:
                tokens.append(buf)
                buf = ""

        for ch in text:
            if cls._word_char(ch):
                buf += ch
            elif ch == " ":
                flush()
                tokens.append(" ")
            else:
                flush()
                tokens.append(ch)
        flush()
        return tokens

    # ---------------- 入口 ----------------

    def process(self, text, max_chars_per_line,
                punctuation_squeeze=True, hanging_punctuation=False,
                pad_odd_halfwidth=True):
        if not text:
            return ("",)

        self.squeeze_on = punctuation_squeeze
        self.hanging_on = hanging_punctuation
        self.pad_odd = pad_odd_halfwidth
        width = max_chars_per_line * 2

        out = []
        for para in text.split("\n"):
            indent = para[:len(para) - len(para.lstrip())]
            para = para[len(indent):].rstrip()
            if not para:
                out.append(indent)
                continue

            indent_w = self._tw(indent)
            if indent_w >= width:
                out.append(indent + para)
                continue

            first_width = (width - indent_w) if indent_w > 0 else None

            lines = self._wrap(self._tokenize(para), width, first_width)
            lines[0] = indent + lines[0]
            out.append("\n".join(self._render(ln) for ln in lines))
        return ("\n".join(out),)

    # ---------------- 核心断行 ----------------

    def _wrap(self, tokens, width, first_width=None):
        """
        first_width：仅第一行使用的宽度上限（用于容纳段首缩进），
        为 None 时所有行同宽。
        """
        lines, cur, cur_w = [], [], 0
        n, i = len(tokens), 0
        while i < n:
            tok = tokens[i]
            limit = first_width if (first_width is not None and not lines) else width

            if tok == " ":
                if cur:
                    cur.append(tok)
                    cur_w += 1
                i += 1
                continue

            w = self._tw(tok)

            if cur_w == 0 and w > limit:
                acc, acc_w = "", 0
                for ch in tok:
                    chw = self._cw(ch)
                    if acc and acc_w + chw > limit:
                        lines.append(acc)
                        acc, acc_w = ch, chw
                    else:
                        acc += ch
                        acc_w += chw
                cur, cur_w = [acc], acc_w
                i += 1
                continue

            if self._is_no_end(tok) and cur:
                j, nxt_w = i + 1, 0
                while j < n:
                    if tokens[j] != " ":
                        nxt_w = self._tw(tokens[j])
                        break
                    j += 1
                if nxt_w and cur_w + w + nxt_w > limit:
                    lines.append("".join(cur))
                    cur, cur_w = [], 0

            if cur_w + w <= limit:
                cur.append(tok)
                cur_w += w
                i += 1
                continue

            if self._is_no_start(tok):
                half = max(1, w // 2)
                if self.squeeze_on and cur_w + half <= limit:
                    cur.append(tok)
                    cur_w += half
                    i += 1
                    continue
                if self.hanging_on:
                    cur.append(tok)
                    cur_w += w
                    i += 1
                    continue
                j = len(cur) - 1
                while j >= 0 and (cur[j] == " " or self._is_no_start(cur[j])):
                    j -= 1
                if j < 0:
                    cur.append(tok)
                    cur_w += w
                    i += 1
                    continue
                moved = cur[j:]
                cur = cur[:j]
                if cur:
                    lines.append("".join(cur))
                cur = moved
                cur_w = sum(self._tw(t) for t in moved)
                cur.append(tok)
                cur_w += w
                i += 1
                continue

            lines.append("".join(cur))
            cur, cur_w = [], 0

        if cur:
            lines.append("".join(cur))
        return lines

    # ---------------- 渲染 ----------------

    def _render(self, line):
        line = line.rstrip()
        if self.pad_odd:
            line = self._pad_odd(line)
        return line


    @classmethod
    def _pad_odd(cls, line):
        hw_all = [i for i, ch in enumerate(line) if cls._hw(ch)]
        if not hw_all or len(hw_all) % 2 == 0:
            return line
        hw_ns = [i for i in hw_all if line[i] != " "]
        if not hw_ns:
            return line
        p, ch = hw_ns[-1], line[hw_ns[-1]]

        if cls._word_char(ch):
            s = p
            while s > 0 and cls._word_char(line[s - 1]):
                s -= 1
            if s > 0 and line[s - 1] != " ":
                return line[:s] + " " + line[s:]          
            e = p
            while e + 1 < len(line) and cls._word_char(line[e + 1]):
                e += 1
            return line[:e + 1] + " " + line[e + 1:]      
        else:
            if p > 0 and line[p - 1] != " ":
                return line[:p] + " " + line[p:]        
            return line[:p + 1] + " " + line[p + 1:]
