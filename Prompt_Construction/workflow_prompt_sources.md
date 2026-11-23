# Sources for the workflow prompts

The numbered profiles follow the order in the S2_Workflows worksheet of Supplementary Table S2. Each entry identifies the source notebook by its content digest (first 16 hexadecimal characters of SHA-256) and gives zero-based cell indices as stored in that notebook. These indices differ from Jupyter execution counts. Cells labeled “batch” contain a batch entry point or saved output. Table S2 separately reports evidence linking a run to selected responses.

| Profile | Workflow | Notebook digest | Cells and functions |
|---|---|---|---|
| W01 | OpenAI-compatible gateway workflow A | `17c4b29fc486ee0f` | prompt and request 9, 16 / batch 13, 19 |
| W02 | OpenAI-compatible gateway workflow B | `ac0f39ef76a469b9` | prompt and request 9 / batch 19, 20 |
| W02 | OpenAI-compatible gateway workflow B | `dd12625738bcf77c` | prompt and request 9 / batch 13 |
| W03 | o1 gateway workflow | `dd12625738bcf77c` | prompt 9 / request 15 / batch 16 |
| W03 | o1 gateway workflow | `17c4b29fc486ee0f` | earlier Chinese definitions 9, 16 |
| W03 | o1 gateway workflow | `f919ce0de5750f44` | rephrased-stem definition 10 |
| W04 | o3 gateway workflow | `ac0f39ef76a469b9` | prompt 9 / request 23 / batch 25 |
| W05 | GPT-5 gateway workflow | `6a56ff33f41ac746` | prompt and request 9 / batch 10 |
| W06 | Kimi gateway workflow | `f33b7759de74d7e1` | prompt and request 9 / batch 10 |
| W07 | Local Ollama workflow A | `5f50330cc4a12766` | prompt and request 6, 12 / batch 10, 15 |
| W08 | Local Ollama workflow B | `6e42cfdb62a007f2` | prompt and request 5 / batch 9, 10 |
| W09 | gpt-oss Ollama workflow | `136e7953f718603a` | prompt and request 5 / batch 6 |
| W10 | Llama DashScope workflow | `22015c125f9708a3` | prompt and request 8, 15 / batch 11, 13, 18 |
| W11 | DeepSeek official workflow A | `f4a5e33e014631c0` | request 8 / prompts 11, 17, 23 / batch 27 |
| W12 | DeepSeek official reasoning workflow | `8eb57ba5b67cc2bc` | prompt and request 11 / batches 14, 16 / later multiple-choice definition 18 |
| W13 | DeepSeek compatible workflow B | `36007b135b2e5a01` | prompt and request 11 / batch 13 |
| W14 | DeepSeek DashScope workflow | `70865686e7f8386c` | prompt and request 9 / batch 13 |
| W14 | DeepSeek DashScope workflow | `25aff1e31702925d` | earlier definitions 10, 17 |
| W15 | Qwen DashScope workflow A | `4f2861ff8f7ff9b8` | prompt and request 9, 15 / batches 13, 18 |
| W16 | Qwen DashScope workflow B | `5e219217c307c61c` | prompt and request 9 / batch 14 |
| W17 | Qwen streaming workflow | `a4c295e74f754516` | prompt and request 13 / batch cells 16–30 |

## Evidence examples

- **Qwen DashScope workflow A (Listing 1).** Cells 9 and 15, each at lines 20–26, preserve the two definitions of `build_prompt`. Lines 1 and 8–18 in both cells contain the displayed request helper. Lines 62–64 call the active prompt function and submit its result. The single-choice and multiple-choice definitions have saved execution counts 189 and 198. Batch cells 18 and 13 have execution counts 202 and 206, respectively. This interleaving limits assignment of a particular definition to individual archived answers.
- **Qwen DashScope workflow B.** Cell 9 tests the length of the stored reference-label string to select an English single-choice or multiple-choice instruction. The user message contains the stem, available options and answer instruction. The reference answer itself is not inserted. The request contains one user message. The saved execution sequence includes a 466-item Qwen2-57B batch on 11 April 2025.
- **DeepSeek official reasoning workflow.** Cell 11 constructs a request from a rephrased stem, available option fields and Chinese answer instructions, and explicitly supplies both system and user messages. Saved output from cell 16 can be linked to 545 selected SRC-05 responses for DeepSeek-V3 under the requested `deepseek-chat` identifier. Execution evidence and source linkage apply to the documented batch.

Profiles reflect client-side code. Whether a separate system message appeared is recorded from the request structure. A locally submitted prompt string is reported under the local interface.
