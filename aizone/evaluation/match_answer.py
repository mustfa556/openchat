import re
import ast

from aizone.evaluation.grading.math_grader import grade_answer


def zs_agieval_match_answer(task_data, response):
    # AGIEval match first capital letter, following original paper implementation
    # https://github.com/microsoft/AGIEval/blob/main/src/post_process.py

    letter_set = {"A", "B", "C", "D", "E", "F"}
    for c in response:
        if c in letter_set:
            return True, c

    return False, ""


def zs_bbh_mc_orca_truthfulqa_orca_match_answer(task_data, response):
    # For BBH & TruthfulQA, match first option letter

    for c in response:
        if c in task_data["options"]:
            return True, c

    return False, ""


def fs_cothub_math_match_answer(task_data, response, max_length=256):
    def _last_boxed_only_string(string):
        idx = string.rfind("\\boxed")
        if idx < 0:
            idx = string.rfind("\\fbox")
            if idx < 0:
                return None

        i = idx
        left_brace_idx = None
        right_brace_idx = None
        num_left_braces_open = 0
        while i < len(string):
            if string[i] == "{":
                num_left_braces_open += 1
                if left_brace_idx is None:
                    left_brace_idx = i
            elif string[i] == "}":
                num_left_braces_open -= 1
                if num_left_braces_open == 0:
                    right_brace_idx = i
                    break

            i += 1
        
        if left_brace_idx is None or right_brace_idx is None:
            return None

        return string[left_brace_idx + 1: right_brace_idx].strip()

    # Match true answer
    ground_truth_answer = _last_boxed_only_string(task_data["_metadata"]["solution"])
    assert ground_truth_answer

    # Match model answer
    is_matched = False

    ans_line = response.split('The answer is')
    if len(ans_line) > 1:
        is_matched = True
        response = ans_line[-1].strip()
    else:
        ans_extracted = _last_boxed_only_string(response)
        if ans_extracted:
            is_matched = True
            response = ans_extracted

    # Grade
    response = response[:max_length]  # To avoid sympy taking too long
    return is_matched, grade_answer(response, ground_truth_answer)


def zs_gpqa_match_answer(task_data, response):
    # Expected to see answer field, otherwise return C.
    ans = response.split("The correct answer is")

    if len(ans) == 1:
        return False, "C"

    ans = ans[1]

    letter_set = {"A", "B", "C", "D"} 
    for c in ans:
        if c in letter_set:
            return True, c

    return False, "C"


def fs_cothub_bbh_match_answer(task_data, response):
    # CoT hub match answer for BBH
    # https://github.com/FranxYao/chain-of-thought-hub/blob/main/BBH/run_bbh_gpt_3.5_turbo.py

    ans_line = response.split('answer is ')

    # Expect to see 'answer is'. If not return whole string
    if len(ans_line) == 1:
        return False, response
    else:
        ans = ans_line[-1].strip()

    if task_data["options"]:
        # Multiple choice, find appearing letter
        options = ['(A)', '(B)', '(C)', '(D)', '(E)', '(F)', '(G)', '(H)', '(I)', '(J)', '(K)', '(L)', '(M)', '(N)', '(O)', '(P)', '(Q)', '(R)', '(S)', '(T)', '(U)', '(V)', '(W)', '(X)', '(Y)', '(Z)']

        for option in options:
            if option in ans:
                return True, option

        return False, ans
    else:
        # Free form, direct return
        if len(ans) and ans[-1] == '.':
            ans = ans[:-1]

        return True, ans


def fs_cothub_gsm8k_match_answer(task_data, response):
    # CoT hub match answer for GSM8k, match last numeric value
    # https://github.com/FranxYao/chain-of-thought-hub/blob/main/gsm8k/gpt3.5turbo_gsm8k_complex.ipynb

    pattern = '\d*\.?\d+'
    pred = re.findall(pattern, response)
    if len(pred) >= 1:
        return True, pred[-1]

    return False, response


def fs_cothub_mmlu_match_answer(task_data, response):
    ans_line = response.split('answer is')

    # Expect to see 'answer is'. If not return C
    if len(ans_line) == 1:
        return False, "(C)"
    else:
        ans = ans_line[-1].strip()
        
    options = ['(A)', '(B)', '(C)', '(D)']
    for option in options:
        if option in ans:
            return True, option

    return False, "(C)"


def coding_humaneval_match_answer(task_data, response):
    # Matching utilities
    def _function_exists(code, func_name):
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return True

        return False

    def _try_match(content, prefix, entrypoint):
        # All markdown code blocks, as well as raw
        code_blocks = [m[1] for m in re.findall(r"(\`{3}.*?\n+)([\s\S]*?)(\n+\`{3})", content)] \
                    + [content]

        for block in code_blocks:
            # Check syntax
            try:
                code_completion = prefix + block
                if _function_exists(code_completion, entrypoint):
                    return code_completion
            except SyntaxError:
                pass

    # Try match with include prefix
    humaneval_task = task_data["_metadata"]
    include_prefix = humaneval_task['prompt'].split('def')[0].strip() + "\n\n"

    result = _try_match(response, include_prefix, humaneval_task["entry_point"])
    if result: 
        return True, {"task_id": humaneval_task["task_id"], "completion": result}

    # If fail then match with function signature
    result = _try_match(response, humaneval_task["prompt"], humaneval_task["entry_point"])
    if result: 
        return True, {"task_id": humaneval_task["task_id"], "completion": result}

    return False, {"task_id": humaneval_task["task_id"], "completion": response}


MATCH_ANSWER_FUNCTION = {
    "zs/agieval": zs_agieval_match_answer,
    "zs/bbh_mc_orca": zs_bbh_mc_orca_truthfulqa_orca_match_answer,
    "zs/truthfulqa_orca": zs_bbh_mc_orca_truthfulqa_orca_match_answer,
    "zs/gpqa": zs_gpqa_match_answer,

    "fs_cothub/bbh": fs_cothub_bbh_match_answer,
    "fs_cothub/gsm8k": fs_cothub_gsm8k_match_answer,
    "fs_cothub/mmlu": fs_cothub_mmlu_match_answer,
    "fs_cothub/math": fs_cothub_math_match_answer,

    "coding/humaneval": coding_humaneval_match_answer
}
