import re
import json
import asyncio
import logging
import asyncio
import traceback
from typing import Any, Dict, Union

import httpx
import numpy as np
from openai import OpenAI, AsyncOpenAI
from numpy._core._multiarray_umath import array
from autoevals.ragas import Faithfulness, ContextRelevancy

from agenta_backend.services.security import sandbox
from agenta_backend.models.shared_models import Error, Result

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_correct_answer(
    data_point: Dict[str, Any], settings_values: Dict[str, Any]
) -> Any:
    """
    Helper function to retrieve the correct answer from the data point based on the settings values.

    Args:
        data_point (Dict[str, Any]): The data point containing the correct answer.
        settings_values (Dict[str, Any]): The settings values containing the key for the correct answer.

    Returns:
        Any: The correct answer from the data point.

    Raises:
        ValueError: If the correct answer key is not provided or not found in the data point.
    """
    correct_answer_key = settings_values.get("correct_answer_key")
    if correct_answer_key is None:
        raise ValueError("No correct answer keys provided.")
    if correct_answer_key not in data_point:
        raise ValueError(
            f"Correct answer column '{correct_answer_key}' not found in the test set."
        )
    return data_point[correct_answer_key]


def get_field_value_from_trace(trace: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    Retrieve the value of the key from the trace data.

    Parameters:
    trace (Dict[str, Any]): The nested dictionary to retrieve the value from.
    key (str): The dot-separated key to access the value.

    Returns:
    Dict[str, Any]: The retrieved value or None if the key does not exist or an error occurs.
    """

    EXCLUDED_KEYS = [
        "start_time",
        "end_time",
        "trace_id",
        "span_id",
        "cost",
        "usage",
        "latency",
    ]
    tree = trace
    fields = key.split(".")

    try:
        for field in fields:
            key = field
            idx = None

            if "[" in field and "]" in field:
                key = field.split("[")[0]
                idx = int(field.split("[")[1].split("]")[0])

            if key in EXCLUDED_KEYS:
                return None

            try:
                tree = tree[key]
                if idx is not None:
                    tree = tree[idx]
            except:
                return None

        return tree
    except Exception as e:
        logger.error(f"Error retrieving trace value from key: {traceback.format_exc()}")
        return None


def get_user_key_from_settings(settings_values: Dict[str, Any], user_key: str) -> Any:
    """
    Retrieve the value of a specified key from the settings values.

    Args:
        settings_values (Dict[str, Any]): The settings values containing the key.
        user_key (str): The key to access from the settings values.

    Returns:
        str | None: The value of the specified key from the settings values, or None if a KeyError is encountered.
    """

    user_key = settings_values.get(user_key, {}).get("default", None)
    return user_key


def auto_exact_match(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    """
    Evaluator function to determine if the output exactly matches the correct answer.

    Args:
        inputs (Dict[str, Any]): The inputs for the evaluation.
        output (str): The output generated by the model.
        data_point (Dict[str, Any]): The data point containing the correct answer.
        app_params (Dict[str, Any]): The application parameters.
        settings_values (Dict[str, Any]): The settings values containing the key for the correct answer.
        lm_providers_keys (Dict[str, Any]): The language model provider keys.

    Returns:
        Result: A Result object containing the evaluation result.
    """
    try:
        correct_answer = get_correct_answer(data_point, settings_values)
        exact_match = True if output == correct_answer else False
        result = Result(type="bool", value=exact_match)
        return result
    except ValueError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=str(e),
            ),
        )
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Exact Match evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_regex_test(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        re_pattern = re.compile(settings_values["regex_pattern"], re.IGNORECASE)
        result = (
            bool(re_pattern.search(output)) == settings_values["regex_should_match"]
        )
        return Result(type="bool", value=result)
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Regex evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def field_match_test(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        correct_answer = get_correct_answer(data_point, settings_values)
        output_json = json.loads(output)
        result = output_json[settings_values["json_field"]] == correct_answer
        return Result(type="bool", value=result)
    except ValueError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=str(e),
            ),
        )
    except Exception as e:  # pylint: disable=broad-except
        logging.debug("Field Match Test Failed because of Error: %s", str(e))
        return Result(type="bool", value=False)


def auto_webhook_test(
    inputs: Dict[str, Any],
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        correct_answer = get_correct_answer(data_point, settings_values)

        with httpx.Client() as client:
            payload = {
                "correct_answer": correct_answer,
                "output": output,
                "inputs": inputs,
            }
            response = client.post(url=settings_values["webhook_url"], json=payload)
            response.raise_for_status()
            response_data = response.json()
            score = response_data.get("score", None)
            if score is None and not isinstance(score, (int, float)):
                return Result(
                    type="error",
                    value=None,
                    error=Error(
                        message="Error during Auto Webhook evaluation; Webhook did not return a score",
                    ),
                )
            if score < 0 or score > 1:
                return Result(
                    type="error",
                    value=None,
                    error=Error(
                        message="Error during Auto Webhook evaluation; Webhook returned an invalid score. Score must be between 0 and 1",
                    ),
                )
            return Result(type="number", value=score)
    except httpx.HTTPError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=f"[webhook evaluation] HTTP - {repr(e)}",
                stacktrace=traceback.format_exc(),
            ),
        )
    except json.JSONDecodeError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=f"[webhook evaluation] JSON - {repr(e)}",
                stacktrace=traceback.format_exc(),
            ),
        )
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message=f"[webhook evaluation] Exception - {repr(e)} ",
                stacktrace=traceback.format_exc(),
            ),
        )


def auto_custom_code_run(
    inputs: Dict[str, Any],
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        result = sandbox.execute_code_safely(
            app_params=app_params,
            inputs=inputs,
            output=output,
            correct_answer=data_point.get(
                "correct_answer", None
            ),  # for backward compatibility
            code=settings_values["code"],
            datapoint=data_point,
        )
        return Result(type="number", value=result)
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Custom Code Evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_ai_critique(
    inputs: Dict[str, Any],
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    """
    Evaluate a response using an AI critique based on provided inputs, output, correct answer, app parameters, and settings.

    Args:
        inputs (Dict[str, Any]): Input parameters for the LLM app variant.
        output (str): The output of the LLM app variant.
        correct_answer_key (str): The key name of the correct answer  in the datapoint.
        app_params (Dict[str, Any]): Application parameters.
        settings_values (Dict[str, Any]): Settings for the evaluation.
        lm_providers_keys (Dict[str, Any]): Keys for language model providers.

    Returns:
        Result: Evaluation result.
    """
    try:
        correct_answer = get_correct_answer(data_point, settings_values)
        openai_api_key = lm_providers_keys["OPENAI_API_KEY"]

        chain_run_args = {
            "llm_app_prompt_template": app_params.get("prompt_user", ""),
            "variant_output": output,
            "correct_answer": correct_answer,
        }

        for key, value in inputs.items():
            chain_run_args[key] = value

        prompt_template = settings_values["prompt_template"]
        messages = [
            {"role": "system", "content": prompt_template},
            {"role": "user", "content": str(chain_run_args)},
        ]

        client = OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", messages=messages, temperature=0.8
        )

        evaluation_output = response.choices[0].message.content.strip()
        return Result(type="text", value=evaluation_output)
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto AI Critique",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_starts_with(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        prefix = settings_values.get("prefix", "")
        case_sensitive = settings_values.get("case_sensitive", True)

        if not case_sensitive:
            output = output.lower()
            prefix = prefix.lower()

        result = Result(type="bool", value=output.startswith(prefix))
        return result
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Starts With evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_ends_with(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        suffix = settings_values.get("suffix", "")
        case_sensitive = settings_values.get("case_sensitive", True)

        if not case_sensitive:
            output = output.lower()
            suffix = suffix.lower()

        result = Result(type="bool", value=output.endswith(suffix))
        return result
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Ends With evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_contains(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        substring = settings_values.get("substring", "")
        case_sensitive = settings_values.get("case_sensitive", True)

        if not case_sensitive:
            output = output.lower()
            substring = substring.lower()

        result = Result(type="bool", value=substring in output)
        return result
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Contains evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_contains_any(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        substrings_str = settings_values.get("substrings", "")
        substrings = [substring.strip() for substring in substrings_str.split(",")]
        case_sensitive = settings_values.get("case_sensitive", True)

        if not case_sensitive:
            output = output.lower()
            substrings = [substring.lower() for substring in substrings]

        result = Result(
            type="bool", value=any(substring in output for substring in substrings)
        )
        return result
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Contains Any evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_contains_all(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        substrings_str = settings_values.get("substrings", "")
        substrings = [substring.strip() for substring in substrings_str.split(",")]
        case_sensitive = settings_values.get("case_sensitive", True)

        if not case_sensitive:
            output = output.lower()
            substrings = [substring.lower() for substring in substrings]

        result = Result(
            type="bool", value=all(substring in output for substring in substrings)
        )
        return result
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Contains All evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_contains_json(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],  # pylint: disable=unused-argument
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        try:
            start_index = output.index("{")
            end_index = output.rindex("}") + 1
            potential_json = output[start_index:end_index]

            json.loads(potential_json)
            contains_json = True
        except (ValueError, json.JSONDecodeError):
            contains_json = False

        return Result(type="bool", value=contains_json)
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Contains JSON evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def flatten_json(json_obj: Union[list, dict]) -> Dict[str, Any]:
    """
    This function takes a (nested) JSON object and flattens it into a single-level dictionary where each key represents the path to the value in the original JSON structure. This is done recursively, ensuring that the full hierarchical context is preserved in the keys.

    Args:
        json_obj (Union[list, dict]): The (nested) JSON object to flatten. It can be either a dictionary or a list.

    Returns:
        Dict[str, Any]: The flattened JSON object as a dictionary, with keys representing the paths to the values in the original structure.
    """

    output = {}

    def flatten(obj: Union[list, dict], path: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{path}.{key}" if path else key
                if isinstance(value, (dict, list)):
                    flatten(value, new_key)
                else:
                    output[new_key] = value

        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                new_key = f"{path}.{index}" if path else str(index)
                if isinstance(value, (dict, list)):
                    flatten(value, new_key)
                else:
                    output[new_key] = value

    flatten(json_obj)
    return output


def compare_jsons(
    ground_truth: Union[list, dict],
    app_output: Union[list, dict],
    settings_values: dict,
):
    """
    This function takes two JSON objects (ground truth and application output), flattens them using the `flatten_json` function, and then compares the fields.

    Args:
        ground_truth (list | dict): The ground truth
        app_output (list | dict): The application output
        settings_values: dict: The advanced configuration of the evaluator

    Returns:
        the average score between both JSON objects
    """

    def normalize_keys(d: Dict[str, Any], case_insensitive: bool) -> Dict[str, Any]:
        if not case_insensitive:
            return d
        return {k.lower(): v for k, v in d.items()}

    def diff(ground_truth: Any, app_output: Any, compare_schema_only: bool) -> float:
        gt_key, gt_value = next(iter(ground_truth.items()))
        ao_key, ao_value = next(iter(app_output.items()))

        if compare_schema_only:
            return (
                1.0 if (gt_key == ao_key and type(gt_value) == type(ao_value)) else 0.0
            )
        return 1.0 if (gt_key == ao_key and gt_value == ao_value) else 0.0

    flattened_ground_truth = flatten_json(ground_truth)
    flattened_app_output = flatten_json(app_output)

    keys = flattened_ground_truth.keys()
    if settings_values.get("predict_keys", False):
        keys = set(keys).union(flattened_app_output.keys())

    cumulated_score = 0.0
    no_of_keys = len(keys)

    compare_schema_only = settings_values.get("compare_schema_only", False)
    case_insensitive_keys = settings_values.get("case_insensitive_keys", False)
    flattened_ground_truth = normalize_keys(
        flattened_ground_truth, case_insensitive_keys
    )
    flattened_app_output = normalize_keys(flattened_app_output, case_insensitive_keys)

    for key in keys:
        ground_truth_value = flattened_ground_truth.get(key, None)
        llm_app_output_value = flattened_app_output.get(key, None)

        key_score = 0.0
        if ground_truth_value and llm_app_output_value:
            key_score = diff(
                {key: ground_truth_value},
                {key: llm_app_output_value},
                compare_schema_only,
            )

        cumulated_score += key_score

    average_score = cumulated_score / no_of_keys
    return average_score


def auto_json_diff(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: Any,
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],  # pylint: disable=unused-argument
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        correct_answer = get_correct_answer(data_point, settings_values)
        average_score = compare_jsons(
            ground_truth=correct_answer,
            app_output=json.loads(output),
            settings_values=settings_values,
        )
        return Result(type="number", value=average_score)
    except (ValueError, json.JSONDecodeError, Exception):
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during JSON diff evaluation",
                stacktrace=traceback.format_exc(),
            ),
        )


def rag_faithfulness(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: Dict[str, Any],
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],  # pylint: disable=unused-argument
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        # Get required keys for rag evaluator
        question_key = get_user_key_from_settings(settings_values, "question_key")
        answer_key = get_user_key_from_settings(settings_values, "answer_key")
        contexts_key = get_user_key_from_settings(settings_values, "contexts_key")

        if None in [question_key, answer_key, contexts_key]:
            raise ValueError(
                "Missing required configuration keys: 'question_key', 'answer_key', or 'contexts_key'. Please check your settings and try again."
            )

        # Get value of required keys for rag evaluator
        question_value = get_field_value_from_trace(output, question_key)
        answer_value = get_field_value_from_trace(output, answer_key)
        contexts_value = get_field_value_from_trace(output, contexts_key)

        if None in [question_value, answer_value, contexts_value]:
            raise ValueError(
                "Missing required key values for rag_evaluator: 'question_value', 'answer_value', or 'contexts_value'. Please check your settings and try again."
            )

        # Initialize RAG evaluator to calculate faithfulness score
        loop = asyncio.get_event_loop()
        faithfulness = Faithfulness()
        eval_score = loop.run_until_complete(
            faithfulness._run_eval_async(
                output=answer_value, input=question_value, context=contexts_value
            )
        )
        return Result(type="number", value=eval_score.score)
    except Exception:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during RAG Faithfulness evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def rag_context_relevancy(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: Dict[str, Any],
    data_point: Dict[str, Any],  # pylint: disable=unused-argument
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],  # pylint: disable=unused-argument
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        # Get required keys for rag evaluator
        question_key = get_user_key_from_settings(settings_values, "question_key")
        answer_key = get_user_key_from_settings(settings_values, "answer_key")
        contexts_key = get_user_key_from_settings(settings_values, "contexts_key")

        if None in [question_key, answer_key, contexts_key]:
            raise ValueError(
                "Missing required configuration keys: 'question_key', 'answer_key', or 'contexts_key'. Please check your settings and try again."
            )

        # Get value of required keys for rag evaluator
        question_value = get_field_value_from_trace(output, question_key)
        answer_value = get_field_value_from_trace(output, answer_key)
        contexts_value = get_field_value_from_trace(output, contexts_key)

        if None in [question_value, answer_value, contexts_value]:
            raise ValueError(
                "Missing required key values for rag_evaluator: 'question_value', 'answer_value', or 'contexts_value'. Please check your settings and try again."
            )

        # Initialize RAG evaluator to calculate context relevancy score
        loop = asyncio.get_event_loop()
        context_rel = ContextRelevancy()
        eval_score = loop.run_until_complete(
            context_rel._run_eval_async(
                output=answer_value, input=question_value, context=contexts_value
            )
        )
        return Result(type="number", value=eval_score.score)
    except Exception:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during RAG Context Relevancy evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)  # pylint: disable=arguments-out-of-order

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def auto_levenshtein_distance(
    inputs: Dict[str, Any],  # pylint: disable=unused-argument
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],  # pylint: disable=unused-argument
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],  # pylint: disable=unused-argument
) -> Result:
    try:
        correct_answer = get_correct_answer(data_point, settings_values)

        distance = levenshtein_distance(output, correct_answer)

        if "threshold" in settings_values:
            threshold = settings_values["threshold"]
            is_within_threshold = distance <= threshold
            return Result(type="bool", value=is_within_threshold)

        return Result(type="number", value=distance)

    except ValueError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=str(e),
            ),
        )
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Levenshtein threshold evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


def auto_similarity_match(
    inputs: Dict[str, Any],
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        correct_answer = get_correct_answer(data_point, settings_values)
        set1 = set(output.split())
        set2 = set(correct_answer.split())
        intersect = set1.intersection(set2)
        union = set1.union(set2)

        similarity = len(intersect) / len(union)

        is_similar = (
            True if similarity > settings_values["similarity_threshold"] else False
        )
        result = Result(type="bool", value=is_similar)
        return result
    except ValueError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=str(e),
            ),
        )
    except Exception as e:  # pylint: disable=broad-except
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Similarity Match evaluation",
                stacktrace=str(traceback.format_exc()),
            ),
        )


async def semantic_similarity(output: str, correct_answer: str, api_key: str) -> float:
    """Calculate the semantic similarity score of the LLM app using OpenAI's Embeddings API.

    Args:
        output (str): the output text
        correct_answer (str): the correct answer text

    Returns:
        float: the semantic similarity score
    """

    openai = AsyncOpenAI(api_key=api_key)

    async def encode(text: str):
        response = await openai.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return np.array(response.data[0].embedding)

    def cosine_similarity(output_vector: array, correct_answer_vector: array) -> float:
        return np.dot(output_vector, correct_answer_vector)

    output_vector = await encode(output)
    correct_answer_vector = await encode(correct_answer)
    similarity_score = cosine_similarity(output_vector, correct_answer_vector)
    return similarity_score


def auto_semantic_similarity(
    inputs: Dict[str, Any],
    output: str,
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        loop = asyncio.get_event_loop()
        openai_api_key = lm_providers_keys["OPENAI_API_KEY"]
        correct_answer = get_correct_answer(data_point, settings_values)

        score = loop.run_until_complete(
            semantic_similarity(
                output=output, correct_answer=correct_answer, api_key=openai_api_key
            )
        )
        return Result(type="number", value=score)
    except Exception:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Semantic Similarity",
                stacktrace=str(traceback.format_exc()),
            ),
        )


EVALUATOR_FUNCTIONS = {
    "auto_exact_match": auto_exact_match,
    "auto_regex_test": auto_regex_test,
    "field_match_test": field_match_test,
    "auto_webhook_test": auto_webhook_test,
    "auto_custom_code_run": auto_custom_code_run,
    "auto_ai_critique": auto_ai_critique,
    "auto_starts_with": auto_starts_with,
    "auto_ends_with": auto_ends_with,
    "auto_contains": auto_contains,
    "auto_contains_any": auto_contains_any,
    "auto_contains_all": auto_contains_all,
    "auto_contains_json": auto_contains_json,
    "auto_json_diff": auto_json_diff,
    "auto_semantic_similarity": auto_semantic_similarity,
    "auto_levenshtein_distance": auto_levenshtein_distance,
    "auto_similarity_match": auto_similarity_match,
    "rag_faithfulness": rag_faithfulness,
    "rag_context_relevancy": rag_context_relevancy,
}


def evaluate(
    evaluator_key: str,
    inputs: Dict[str, Any],
    output: Union[str, Dict[str, Any]],
    data_point: Dict[str, Any],
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    evaluation_function = EVALUATOR_FUNCTIONS.get(evaluator_key, None)
    if not evaluation_function:
        return Result(
            type="error",
            value=None,
            error=Error(
                message=f"Evaluation method '{evaluator_key}' not found.",
            ),
        )
    try:
        return evaluation_function(
            inputs,
            output,
            data_point,
            app_params,
            settings_values,
            lm_providers_keys,
        )
    except Exception as exc:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error occurred while running {evaluator_key} evaluation. ",
                stacktrace=str(exc),
            ),
        )
