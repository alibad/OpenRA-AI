# Third-party model notices

The OpenRA AI Local AI Pack redistributes pinned, unmodified model files. The
pack manifest records the exact upstream revision, byte length, and SHA-256 for
every file.

| Component | Upstream | License |
| --- | --- | --- |
| Qwen3-VL-2B-Instruct GGUF and vision projector | [Qwen](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF) | Apache-2.0 |
| Whisper `base.en` weights | [OpenAI Whisper](https://github.com/openai/whisper) and [whisper.cpp conversion](https://huggingface.co/ggerganov/whisper.cpp) | MIT |
| Kokoro-82M ONNX model and voices | [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) and [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | Apache-2.0 model; MIT runtime |

The Windows local-AI pack also contains the checksum-pinned CPU builds of
[llama.cpp](https://github.com/ggml-org/llama.cpp) and
[whisper.cpp](https://github.com/ggml-org/whisper.cpp). Both runtimes are MIT
licensed. Their exact release revisions and archive checksums are recorded in
`ai-runtime.lock.json`.

The inference runtimes are packaged separately for each operating system and
retain their own license files. Review upstream model cards and voice notices
before changing a pinned model or voice set.
