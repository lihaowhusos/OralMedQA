"""Supplementary Code Listing 1. Qwen DashScope workflow A.
The cell excerpts are displayed separately, as in the archived notebook.
"""
import pandas as pd


# Cell 9. Single-choice prompt
def build_prompt(row):
    prompt = f"题目：{row['题目']}\n"
    options = [f"{option_name}: {row[option_name]}" for option_name in ['选项A', '选项B', '选项C', '选项D', '选项E', '选项F', '选项G'] if pd.notna(row[option_name])]
    prompt += '\n'.join(options) + '\n'
    prompt += "题目是单选题，仅返回选项字母,如A、B、C、D等，不要解释。\n"
    prompt += "请选出题目的正确答案。\n"
    return prompt


# Cell 15. Multiple-choice prompt
def build_prompt(row):
    prompt = f"题目：{row['题目']}\n"
    options = [f"{option_name}: {row[option_name]}" for option_name in ['选项A', '选项B', '选项C', '选项D', '选项E', '选项F', '选项G'] if pd.notna(row[option_name])]
    prompt += '\n'.join(options) + '\n'
    prompt += "题目是多选题，仅返回选项字母,如AB、ABC、CD、BD等，不要解释。\n"
    prompt += "请选出题目的正确答案。\n"
    return prompt


# Cells 9 and 15. Request helper
def generate_completion(client, prompt, model_name, display_prompt=False, calls_per_minute=60):
    # Pacing and diagnostic logging omitted (lines 2-7).
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=5000,  # 根据需要调整
        temperature=0,  # 设为0以获得确定性回答
        stream=False  # 设置为 True 可启用流式输出
    )
    return response.choices[0].message.content
