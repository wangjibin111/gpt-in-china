import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import asyncio
import edge_tts
from playsound import playsound
import pygame

# API配置（使用你最初提供的）
API_CONFIG = {
    "url": "https://free.v36.cm/v1/chat/completions",
    "headers": {
        "Authorization": "Bearer sk-0RP3di0ONRrDfNny3d5b23A6048f44DeB2CdF1534f8f6c01",
        "Content-Type": "application/json"
    }
}

# 仅保留两种模型
SUPPORTED_MODELS = [
    "gpt-4o-mini",
    "gpt-3.5-turbo"
]

class VerticalScrolledFrame(ttk.Frame):
    """自定义带垂直滚动条的容器"""
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.vscrollbar = ttk.Scrollbar(self, orient="vertical")
        self.vscrollbar.pack(side="right", fill="y")
        self.canvas = tk.Canvas(self, yscrollcommand=self.vscrollbar.set, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscrollbar.config(command=self.canvas.yview)
        self.interior = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.interior.bind("<Configure>", self._configure_interior)
        self.canvas.bind("<Configure>", self._configure_canvas)
        
    def _configure_interior(self, event):
        size = (self.interior.winfo_reqwidth(), self.interior.winfo_reqheight())
        self.canvas.config(scrollregion=(0, 0, size[0], size[1]))
                           
    def _configure_canvas(self, event):
        if self.interior.winfo_reqwidth() != self.canvas.winfo_width():
            self.canvas.itemconfigure("all", width=self.canvas.winfo_width())

class GPTAssistant:
    def __init__(self, root):
        self.root = root
        self.setup_ui()
        self.stop_streaming = False
        self.message_history = []  # 新增：存储对话历史

    def setup_ui(self):
        """初始化界面"""
        self.root.title("AI问答助手 (GPT-4o-mini & GPT-3.5-turbo)")
        self.root.geometry("680x600")

        # 主滚动框架
        self.main_frame = VerticalScrolledFrame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # 模型选择
        model_frame = ttk.LabelFrame(self.main_frame.interior, text="模型选择", padding=10)
        model_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(model_frame, text="选择模型:").pack(side="left")
        self.model_var = tk.StringVar()
        self.model_combobox = ttk.Combobox(
            model_frame,
            textvariable=self.model_var,
            values=SUPPORTED_MODELS,
            state="readonly",
            width=15
        )
        self.model_combobox.current(0)
        self.model_combobox.pack(side="left", padx=5)

        # 参数设置
        param_frame = ttk.LabelFrame(self.main_frame.interior, text="参数设置", padding=10)
        param_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(param_frame, text="max_tokens:").pack(side="left")
        self.max_tokens_entry = ttk.Entry(param_frame, width=8)
        self.max_tokens_entry.insert(0, "1024")
        self.max_tokens_entry.pack(side="left", padx=5)
        ttk.Label(param_frame, text="(1-4096)").pack(side="left")

        # 输入框
        input_frame = ttk.LabelFrame(self.main_frame.interior, text="输入问题", padding=10)
        input_frame.pack(fill="x", padx=5, pady=5)
        
        self.input_text = tk.Text(
            input_frame,
            height=8,
            wrap="word",
            font=("Microsoft YaHei", 10)
        )
        self.input_text.pack(fill="x", padx=5, pady=5)

        # 输出框
        output_frame = ttk.LabelFrame(self.main_frame.interior, text="AI回答", padding=10)
        output_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.output_text = tk.Text(
            output_frame,
            height=15,
            wrap="word",
            font=("Microsoft YaHei", 10),
            state="disabled"
        )
        self.output_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 输出框滚动条
        output_scroll = ttk.Scrollbar(output_frame, command=self.output_text.yview)
        output_scroll.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=output_scroll.set)

        # 按钮区域
        button_frame = ttk.Frame(self.main_frame.interior)
        button_frame.pack(fill="x", padx=5, pady=5)

        self.submit_button = ttk.Button(
            button_frame,
            text="发送问题",
            command=self.start_request_thread
        )
        self.submit_button.pack(side="left", padx=5)

        self.stop_button = ttk.Button(
            button_frame,
            text="停止生成",
            command=self.stop_stream,
            state="disabled"
        )
        self.stop_button.pack(side="left", padx=5)

        # 在现有按钮后添加清除按钮
        self.clear_button = ttk.Button(
            button_frame,
            text="清除对话",
            command=self.clear_context,
            style="TButton"
        )
        self.clear_button.pack(side="left", padx=5)

        # 添加朗读按钮
        self.read_button = ttk.Button(
            button_frame,
            text="朗读回答（可能会把markdown原封不动说出来）",
            command=self.start_read_thread
        )
        self.read_button.pack(side="left", padx=5)

    def start_read_thread(self):
        """启动朗读线程"""
        threading.Thread(target=self.read_response, daemon=True).start()

    async def _read_text(self, text):
        """使用 edge-tts 朗读文本"""
        communicate = edge_tts.Communicate(text, voice="zh-CN-XiaoyiNeural")
        import tempfile
        import os
        try:
            # 初始化 pygame 混音器
            pygame.mixer.init()
            # 创建临时文件来保存音频，设置 delete=False 避免自动删除
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                # 异步迭代获取音频流并写入临时文件
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        temp_file.write(chunk["data"])
                # 刷新缓冲区，确保数据写入文件
                temp_file.flush()
            # 加载并播放音频
            pygame.mixer.music.load(temp_file.name)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            self.update_output(f"\n❌ 播放音频出错: {str(e)}\n", is_end=True)
        finally:
            # 确保无论是否出错，临时文件都会被删除
            if 'temp_file' in locals() and os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            # 关闭 pygame 混音器
            pygame.mixer.quit()

    def read_response(self):
        """读取输出框内容并朗读"""
        self.output_text.config(state="normal")
        text = self.output_text.get("1.0", tk.END).strip()
        self.output_text.config(state="disabled")
        try:
            asyncio.run(self._read_text(text))
        except Exception as e:
            self.update_output(f"\n❌ 朗读错误: {str(e)}\n", is_end=True)

    def start_request_thread(self):
        """启动请求线程"""
        self.stop_streaming = False
        self.submit_button.config(state="disabled")
        self.stop_button.config(state="normal")
        threading.Thread(target=self.get_response, daemon=True).start()

    def stop_stream(self):
        """停止流式输出"""
        self.stop_streaming = True
        self.stop_button.config(state="disabled")

    def update_output(self, content, is_end=False):
        """线程安全的输出更新"""
        self.output_text.after(0, lambda: self._update_output(content, is_end))

    def _update_output(self, content, is_end):
        """实际更新输出"""
        self.output_text.config(state="normal")
        if is_end:
            self.output_text.insert("end", content + "\n\n")
        else:
            self.output_text.insert("end", content)
        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def clear_context(self):
        """清除上下文，开始新对话"""
        self.stop_streaming = True  # 设置停止标志
        self.stop_button.config(state="disabled")  # 禁用停止按钮
        self.submit_button.config(state="normal")  # 启用发送按钮
        self.message_history = []  # 清空历史
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, "🔄 上下文已清除，开始新对话\n")
        self.output_text.config(state="disabled")

    def get_response(self):
        """获取AI响应"""
        user_input = self.input_text.get("1.0", "end").strip()
        max_tokens = self.max_tokens_entry.get().strip()
        model = self.model_var.get()

        # 输入验证
        if not user_input:
            self.update_output("⚠️ 请输入您的问题！", is_end=True)
            self.submit_button.config(state="normal")
            return

        if not max_tokens.isdigit() or int(max_tokens) <= 0 or int(max_tokens) > 4096:
            self.update_output("⚠️ max_tokens 必须是1-4096之间的整数！", is_end=True)
            self.submit_button.config(state="normal")
            return

        # 更新消息历史（在准备payload之前添加）
        self.message_history.append({"role": "user", "content": user_input})
        
        # 准备请求
        payload = {
            "model": model,
            "messages": self.message_history,  # 使用历史消息
            "max_tokens": int(max_tokens),
            "stream": True  # 启用流式响应
        }

        try:
            self.update_output(f"🚀 {model} 正在思考...\n", is_end=True)
            
            full_response = ""
            with requests.post(
                API_CONFIG["url"],
                json=payload,
                headers=API_CONFIG["headers"],
                stream=True,
                timeout=30
            ) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if self.stop_streaming:
                        self.update_output("\n⏹️ 已停止生成", is_end=True)
                        break
                    
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data:"):
                            try:
                                chunk = json.loads(decoded_line[5:])
                                if "content" in chunk["choices"][0]["delta"]:
                                    content = chunk["choices"][0]["delta"]["content"]
                                    full_response += content
                                    self.update_output(content)
                                if "[DONE]" in decoded_line:
                                    # 在成功获取响应后保存AI回复
                                    if not self.stop_streaming:
                                        self.message_history.append({"role": "assistant", "content": full_response})
                            except json.JSONDecodeError:
                                pass

            if not self.stop_streaming:
                self.update_output("\n\n✅ 生成完成", is_end=True)
                
        except Exception as e:
            self.update_output(f"\n❌ 错误: {str(e)}\n", is_end=True)
        finally:
            self.submit_button.config(state="normal")
            self.stop_button.config(state="disabled")

def check_dependencies():
    """检查依赖"""
    try:
        import requests
        import edge_tts
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        if messagebox.askyesno("缺少依赖", "需要安装requests和edge-tts库，是否立即安装？"):
            import os, sys
            os.system(f"{sys.executable} -m pip install requests edge-tts")
            try:
                import requests
                import edge_tts
            except ImportError:
                messagebox.showerror("错误", "安装失败，请手动执行: pip install requests edge-tts")
                sys.exit(1)
        else:
            sys.exit(1)

if __name__ == "__main__":
    check_dependencies()
    root = tk.Tk()
    app = GPTAssistant(root)
    root.mainloop()
