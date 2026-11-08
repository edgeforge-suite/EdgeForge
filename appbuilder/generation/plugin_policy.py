"""Targeted dependencies in proven build-plugin realms, never the app BOM."""

from types import MappingProxyType

PLUGIN_REALM_POLICY_ID = "ef-v5-plugin-realms-1"
PLUGIN_REALM_DEPENDENCIES = MappingProxyType({
    "maven-clean-plugin": (("org.codehaus.plexus", "plexus-utils", "4.0.3"),),
    "maven-compiler-plugin": (
        ("commons-io", "commons-io", "2.14.0"),
        ("org.codehaus.plexus", "plexus-utils", "4.0.3"),
    ),
    "maven-resources-plugin": (("org.codehaus.plexus", "plexus-utils", "3.6.1"),),
    "spring-boot-maven-plugin": (
        ("org.apache.commons", "commons-lang3", "3.18.0"),
        ("org.codehaus.plexus", "plexus-utils", "3.6.1"),
        ("tools.jackson.core", "jackson-core", "3.1.7"),
        ("tools.jackson.core", "jackson-databind", "3.1.7"),
    ),
})


def build_plugins(enabled: bool) -> list[str]:
    plugins = PLUGIN_REALM_DEPENDENCIES if enabled else {"spring-boot-maven-plugin": ()}
    lines = []
    for artifact, dependencies in plugins.items():
        group = "org.springframework.boot" if artifact == "spring-boot-maven-plugin" else "org.apache.maven.plugins"
        lines.extend(["            <plugin>", f"                <groupId>{group}</groupId>",
                      f"                <artifactId>{artifact}</artifactId>"])
        if dependencies:
            lines.append("                <dependencies>")
            for group, name, version in dependencies:
                lines.extend(["                    <dependency>", f"                        <groupId>{group}</groupId>",
                              f"                        <artifactId>{name}</artifactId>",
                              f"                        <version>{version}</version>", "                    </dependency>"])
            lines.append("                </dependencies>")
        lines.append("            </plugin>")
    return lines
