import shutil

import pytest
import yaml

from escalate_anything import advisor
from escalate_anything.registry import Registry

from .conftest import FIXTURES


@pytest.fixture
def world(tmp_path):
    """The fixture registry plus an EU bloc, an EU rule, an EU regulator and an EU airline."""
    root = tmp_path / "registry"
    shutil.copytree(FIXTURES, root)
    (root / "countries").mkdir()
    (root / "countries" / "eu.yaml").write_text(yaml.safe_dump(
        {"id": "eu", "name": "European Union", "kind": "bloc", "members": ["de", "fr"], "associated": ["no"], "status": "in_progress"}))
    (root / "countries" / "gb.yaml").write_text(yaml.safe_dump({"id": "gb", "name": "United Kingdom", "kind": "country", "status": "in_progress"}))
    rule = yaml.safe_load((root / "rules" / "example-refund-rule.yaml").read_text())
    rule.update(id="eu-example-rule", jurisdiction="eu", title="EU example rule")
    (root / "rules" / "eu-example-rule.yaml").write_text(yaml.safe_dump(rule))
    sectors = yaml.safe_load((root / "sectors.yaml").read_text())
    sectors["regulators"].append({"id": "eu-example-body", "name": "EU example enforcement body"})
    (root / "sectors.yaml").write_text(yaml.safe_dump(sectors))
    regulator = yaml.safe_load((root / "regulators" / "us-dot.yaml").read_text())
    regulator.update(id="eu-example-body", name="EU example enforcement body", country="eu", level="supranational")
    (root / "regulators" / "eu-example-body.yaml").write_text(yaml.safe_dump(regulator))
    company = yaml.safe_load((root / "companies" / "airline" / "example-air.yaml").read_text())
    company.update(id="euro-air", name="Euro Air", aliases=["euro air"], countries=["eu", "gb"])
    company.pop("official_domains", None)
    (root / "companies" / "airline" / "euro-air.yaml").write_text(yaml.safe_dump(company))
    return Registry.load(root)


def test_world_validates(world):
    assert world.validate() == []


def test_jurisdictions_include_blocs_and_states(world):
    assert advisor.jurisdictions(world, "de") == {"international", "de", "eu"}
    assert advisor.jurisdictions(world, "no") == {"international", "no", "eu"}
    assert advisor.jurisdictions(world, "gb") == {"international", "gb"}
    assert advisor.jurisdictions(world, None, "ca") == {"international", "us", "us-federal", "us-ca"}


def test_rules_follow_the_country(world):
    def ids(country):
        return {r["id"] for r in advisor.rules_for(world, None, None, country=country)["in_force"]}

    assert "eu-example-rule" in ids("de")
    assert "eu-example-rule" not in ids("gb")
    assert "eu-example-rule" not in ids("us")
    assert "example-refund-rule" in ids("us")  # us-federal


def test_company_countries_and_regulators(world):
    euro = world.companies["euro-air"]
    assert advisor.company_countries(euro) == ["eu", "gb"]
    assert advisor.company_countries(world.companies["example-air"]) == ["us"]
    assert advisor.serves(world, euro, "fr") and advisor.serves(world, euro, "gb")
    assert not advisor.serves(world, euro, "us")
    found = advisor.find_regulators(world, "airline", country="de")
    assert [r["id"] for r in found["regulators"]] == ["eu-example-body"]
    assert "federal" in advisor.find_regulators(world, "airline")


def test_unknown_country_is_reported(world, tmp_path):
    company = dict(world.companies["euro-air"], countries=["xx"])
    path = world.files["company:euro-air"]
    path.write_text(yaml.safe_dump(company))
    problems = Registry.load(path.parents[2]).validate()
    assert any("unknown country 'xx'" in p.message for p in problems)
