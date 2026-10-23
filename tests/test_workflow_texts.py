import runpy
from pathlib import Path
import pytest

main = runpy.run_path(str(Path(__file__).parents[1] / "examples/workflow_texts.py"))["main"]


def document(status, text="usable article text", **extra):
    return {"filename": "article.pdf", "status": status,
            "result": {"document": {"md_content": text}}, **extra}


def test_partial_success_preserves_each_document():
    docs = [document("success", "first"), document("partial_success", "partial article")]
    assert main([{"documents": docs}], "") == {"texts": ["first", "partial article"], "files_count": 2}


@pytest.mark.parametrize("doc", [document("failure"), document("partial_success", "  "),
                                  document("partial_success", inline_text_omitted=True)])
def test_unusable_documents_still_fail(doc):
    with pytest.raises(ValueError):
        main([{"documents": [doc]}], "fallback must not mask failure")


def test_truncated_fallback_still_fails():
    with pytest.raises(ValueError):
        main([], "text [Text truncated for Dify; full exports are in the ZIP.]")
