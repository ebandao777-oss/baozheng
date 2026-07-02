import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "generate_complaint_docx.py"
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_examples.py"
CATEGORY_VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_category_coverage.py"
EXPECTED_FIRST_FIELD_PREFIX = "说明"
EXPECTED_PLAINTIFF_LABEL = "原告(自然人)"


def derive_example_name(slug: str) -> str:
    """根据 slug 推导 example 文件名，命名约定：{slug}-data.json。"""
    return f"{slug}-data.json"


def load_script_module():
    spec = importlib.util.spec_from_file_location("generate_complaint_docx", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_examples", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_category_validator_module():
    spec = importlib.util.spec_from_file_location("validate_category_coverage", CATEGORY_VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenerateComplaintDocxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_script_module()
        cls.validator = load_validator_module()
        cls.category_validator = load_category_validator_module()
        cls.cases = cls.module.discover_cases(SKILL_ROOT)
        cls.case_examples = cls._derive_case_examples()
        cls.criminal_templates = cls._derive_criminal_templates()

    @classmethod
    def _derive_case_examples(cls) -> dict[str, str]:
        """自动从 discover_cases 结果推导 case_code → example_name 映射。"""
        mapping: dict[str, str] = {}
        for case in cls.cases:
            example_name = derive_example_name(case.slug)
            example_path = SKILL_ROOT / "examples" / example_name
            if not example_path.exists():
                raise FileNotFoundError(
                    f"Missing example for case {case.code} (slug={case.slug}): {example_path}"
                )
            mapping[case.code] = example_name
        return mapping

    @classmethod
    def _derive_criminal_templates(cls) -> dict[str, str]:
        """自动推导刑事材料 template 文件名 → example 文件名 映射。"""
        return {
            case.template_path.name: derive_example_name(case.slug)
            for case in cls.cases
            if not case.code.isdigit()
        }

    def test_discovers_all_case_template_pairs(self):
        cases = self.module.discover_cases(SKILL_ROOT)
        case_codes = {item.code for item in cases}
        civil_codes = {code for code in case_codes if code.isdigit()}
        criminal_codes = case_codes - civil_codes
        self.assertGreaterEqual(len(civil_codes), 34)
        self.assertGreaterEqual(len(criminal_codes), 5)
        self.assertTrue(all(item.case_path.exists() for item in cases))
        self.assertTrue(all(item.template_path.exists() for item in cases))

    def test_private_lending_template_can_be_parsed(self):
        cases = self.module.discover_cases(SKILL_ROOT)
        selected = self.module.select_case(cases, "01")
        text = self.module.read_text(selected.template_path)
        title, subtitle = self.module.parse_title(text)
        fields = self.module.parse_fields(text)

        self.assertEqual("民事起诉状", title)
        self.assertIn("民间借贷", subtitle)
        self.assertGreaterEqual(len(fields), 30)
        self.assertEqual(EXPECTED_FIRST_FIELD_PREFIX, fields[0].label[:2])

    def test_private_lending_data_can_fill_fields(self):
        cases = self.module.discover_cases(SKILL_ROOT)
        selected = self.module.select_case(cases, "01")
        text = self.module.read_text(selected.template_path)
        fields = self.module.parse_fields(text)
        data = self.module.load_data(str(SKILL_ROOT / "examples" / "private-lending-data.json"))

        filled_fields, matched_labels = self.module.apply_data(fields, data)

        self.assertGreaterEqual(len(matched_labels), 8)
        self.assertIn(EXPECTED_PLAINTIFF_LABEL, matched_labels)
        self.assertIn("张三", "\n".join(field.placeholder for field in filled_fields))

    def test_generated_docx_contains_filled_data(self):
        cases = self.module.discover_cases(SKILL_ROOT)
        selected = self.module.select_case(cases, "01")
        text = self.module.read_text(selected.template_path)
        title, subtitle = self.module.parse_title(text)
        fields = self.module.parse_fields(text)
        data = self.module.load_data(str(SKILL_ROOT / "examples" / "private-lending-data.json"))
        filled_fields, _ = self.module.apply_data(fields, data)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "private-lending.docx"
            self.module.create_docx(title, subtitle, filled_fields, output_path)
            self.assertTrue(output_path.exists())
            with ZipFile(output_path) as docx_file:
                document_xml = docx_file.read("word/document.xml").decode("utf-8")
            self.assertIn("张三", document_xml)
            self.assertIn("100000", document_xml)

    def test_all_case_examples_can_fill_and_generate_docx(self):
        civil_examples = {k: v for k, v in self.case_examples.items() if k.isdigit()}

        with tempfile.TemporaryDirectory() as temp_dir:
            for case_code, example_name in civil_examples.items():
                with self.subTest(case_code=case_code):
                    selected = self.module.select_case(self.cases, case_code)
                    text = self.module.read_text(selected.template_path)
                    title, subtitle = self.module.parse_title(text)
                    fields = self.module.parse_fields(text)
                    data = self.module.load_data(str(SKILL_ROOT / "examples" / example_name))
                    filled_fields, matched_labels = self.module.apply_data(fields, data)

                    self.assertGreaterEqual(len(matched_labels), 1)
                    output_path = Path(temp_dir) / f"{case_code}.docx"
                    self.module.create_docx(title, subtitle, filled_fields, output_path)
                    self.assertTrue(output_path.exists())
                    with ZipFile(output_path) as docx_file:
                        self.assertIn("word/document.xml", docx_file.namelist())

    def test_criminal_templates_can_parse_and_generate_docx(self):
        criminal_examples = {k: v for k, v in self.case_examples.items() if not k.isdigit()}

        with tempfile.TemporaryDirectory() as temp_dir:
            for case_code, example_name in criminal_examples.items():
                with self.subTest(case_code=case_code):
                    selected = self.module.select_case(self.cases, case_code)
                    text = self.module.read_text(selected.template_path)
                    title, subtitle = self.module.parse_title(text)
                    fields = self.module.parse_fields(text)

                    self.assertGreaterEqual(len(fields), 5)
                    data = self.module.load_data(str(SKILL_ROOT / "examples" / example_name))
                    filled_fields, matched_labels = self.module.apply_data(fields, data)

                    self.assertGreaterEqual(len(matched_labels), 1)
                    output_path = Path(temp_dir) / f"{case_code}.docx"
                    self.module.create_docx(title, subtitle, filled_fields, output_path)
                    self.assertTrue(output_path.exists())
                    with ZipFile(output_path) as docx_file:
                        self.assertIn("word/document.xml", docx_file.namelist())

    def test_all_examples_pass_quality_gate(self):
        results = self.validator.validate_examples(SKILL_ROOT)
        expected_count = len(list((SKILL_ROOT / "examples").glob("*-data.json")))
        self.assertEqual(expected_count, len(results))
        failures = {item.file: item.missing_rules for item in results if not item.passed}
        self.assertEqual({}, failures)

    def test_criminal_material_templates_have_examples(self):
        for template_name, example_name in self.criminal_templates.items():
            with self.subTest(template=template_name):
                template_path = SKILL_ROOT / "assets" / template_name
                example_path = SKILL_ROOT / "examples" / example_name
                self.assertTrue(template_path.exists())
                self.assertTrue(example_path.exists())
                self.assertIn("风险提示", template_path.read_text(encoding="utf-8"))

    def test_legal_category_coverage_gate(self):
        results = self.category_validator.validate_category_coverage(SKILL_ROOT)
        failures = {item.name: item.missing for item in results if not item.passed}
        self.assertEqual({}, failures)

    def test_stale_reference_paths_do_not_return(self):
        stale_patterns = [
            "A-法律咨询.md",
            "B-起诉状起草.md",
            "C-深度分析.md",
            "common-*",
            "references/*-模块速览.md",
            "references/{案由}-模块速览.md",
        ]
        content = "\n".join(path.read_text(encoding="utf-8") for path in SKILL_ROOT.rglob("*.md"))
        for pattern in stale_patterns:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, content)


if __name__ == "__main__":
    unittest.main()
