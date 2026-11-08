"""Isolated DTO mapping proof using Jackson libraries from an assessed app jar."""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

from appbuilder.generation.java_emitter import _render_dto
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import CanonicalEntity, CanonicalField, CanonicalFieldType
from appbuilder.target_profiles.catalog import TARGET_PROFILES

DRIVER = """import java.util.LinkedHashMap;
import tools.jackson.databind.json.JsonMapper;
public class DtoPropertyProbe {
    public static void main(String[] args) throws Exception {
        var mapper = JsonMapper.builder().findAndAddModules().build();
        var type = Class.forName("proof.dto." + args[0]);
        var value = mapper.readValue(args[1], type);
        var fields = new LinkedHashMap<String, Object>();
        for (var field : type.getDeclaredFields()) {
            field.setAccessible(true);
            fields.put(field.getName(), field.get(value));
        }
        var result = new LinkedHashMap<String, Object>();
        result.put("wire", mapper.readTree(mapper.writeValueAsString(value)));
        result.put("canonical", fields);
        System.out.println(mapper.writeValueAsString(result));
    }
}
"""


def verify_dto_properties(root: Path, jar: Path, java_home: Path, payment_metadata) -> list[dict]:
    root.mkdir(parents=True, exist_ok=False)
    libs, classes = root / "lib", root / "classes"
    libs.mkdir()
    classes.mkdir()
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.startswith("BOOT-INF/lib/jackson-") and name.endswith(".jar"):
                (libs / Path(name).name).write_bytes(archive.read(name))
    classpath = ":".join(str(path) for path in sorted(libs.glob("*.jar")))
    if not classpath:
        raise AssertionError("No packaged Jackson libraries for DTO proof")
    driver = root / "DtoPropertyProbe.java"
    driver.write_text(DRIVER)
    entity = next(e for e in payment_metadata.entities if e.name == "InternationalPayment")
    payment_fields = {field.name: field for field in entity.fields}
    wires = ["InternationalPaymentId", "ConsentId", "Status", "StatusUpdateDateTime", "CurrencyOfTransfer", "InstructedAmount"]
    values = ["ROW-A", "consent-proof", "AcceptedSettlementInProcess", "2026-10-13T12:00:00", "USD", "42.50"]
    mappings = [m for m in payment_metadata.mappings if m.operation_name == "CreateInternationalPayments"
                and ".response." in m.source_path]
    targets = {m.source_path.rsplit(".", 1)[1]: m.target_path.split(".", 1)[1] for m in mappings}
    cases = []
    for label, old_names in (("ControlPayment", True), ("CandidatePayment", False)):
        fields = []
        for wire, value in zip(wires, values, strict=True):
            canonical = targets[wire]
            field = payment_fields[canonical].model_copy(deep=True)
            if old_names and wire != "InstructedAmount":
                canonical = wire[:1].lower() + wire[1:]
            field.name = canonical
            fields.append((field, wire, value))
        cases.append((label, fields))
    for label, canonical, wire in (
        ("Plain", "customerId", "customerId"), ("Renamed", "customerId", "customer_id"),
        ("Pascal", "ConsentId", "ConsentId"), ("LowerWire", "ConsentId", "consentId"),
        ("Acronym", "uRL", "link"), ("Snake", "external_code", "external_code"),
    ):
        cases.append((label, [(CanonicalField(name=canonical, type=CanonicalFieldType.STRING,
            required=False, source_paths=[]), wire, "value-" + label)]))
    cases.append(("Distinct", [(CanonicalField(name=canonical, type=kind, required=False, source_paths=[]), wire, value)
        for canonical, wire, kind, value in (
            ("URL", "URL", CanonicalFieldType.STRING, "uppercase-url"),
            ("url", "link", CanonicalFieldType.STRING, "lowercase-url"),
            ("enabled", "enabled", CanonicalFieldType.BOOLEAN, False),
            ("quantity", "quantity", CanonicalFieldType.INTEGER, 17),
        )]))
    sources = [driver]
    for label, fields in cases:
        source = root / (label + ".java")
        source.write_text(_render_dto(class_name=label, package_name="proof.dto",
            entity=CanonicalEntity(name="Record", fields=[field for field, _, _ in fields]),
            field_mappings=[FieldMapping(contract_name="api", direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="create", source_path="api.create.request." + wire,
                target_path="Record." + field.name) for field, wire, _ in fields],
            emit_validation_annotations=False, target_profile=TARGET_PROFILES[payment_metadata.target_profile],
            source_manifest="isolated-dto-fixture", generation_run_id="dto-property-proof"))
        sources.append(source)
    subprocess.run([str(java_home / "bin/javac"), "-cp", classpath, "-d", str(classes),
        *map(str, sources)], check=True, capture_output=True, text=True, timeout=60)
    receipts = []
    for label, fields in cases:
        expected = {wire: value for _, wire, value in fields}
        command = [str(java_home / "bin/java"), "-cp", str(classes) + ":" + classpath,
            "DtoPropertyProbe", label]
        run = subprocess.run([*command, json.dumps(expected)], check=True, capture_output=True, text=True, timeout=30)
        result = json.loads(run.stdout)
        expected_canonical = {field.name: value for field, _, value in fields}
        for key, values_by_name in (("wire", expected), ("canonical", expected_canonical)):
            if result[key] != values_by_name or any(type(result[key][name]) is not type(value)
                    for name, value in values_by_name.items()):
                raise AssertionError(f"{label}: changed {key} names, values or types: {result}")
        aliases = sorted({wire[:1].lower() + wire[1:] for _, wire, _ in fields
            if wire[:1].isupper()} - expected.keys())
        alias_observations = []
        for alias in aliases:
            alias_run = subprocess.run([*command, json.dumps({alias: "unintended"})],
                capture_output=True, text=True, timeout=30)
            if alias_run.returncode == 0:
                alias_result = json.loads(alias_run.stdout)
                if "unintended" in alias_result["canonical"].values() or alias in alias_result["wire"]:
                    raise AssertionError(f"{label}: unintended input alias {alias} bound a property")
            alias_observations.append({"alias": alias, "handling": "ignored-unbound" if alias_run.returncode == 0 else "rejected"})
        receipts.append({"case": label, "expected": expected, **result, "input_aliases": alias_observations})
    (root / "results.json").write_text(json.dumps({"cases": receipts,
        "jackson_libraries": sorted(path.name for path in libs.glob("*.jar")),
        "scope": "isolated current-renderer DTOs; old-name control is not historical base-app runtime"}, indent=2) + "\n")
    return receipts
