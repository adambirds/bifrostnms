/** @type {import('stylelint').Config} */
const config = {
  extends: ["stylelint-config-standard"],
  rules: {
    "at-rule-no-unknown": [
      true,
      {
        ignoreAtRules: [
          "tailwind",
          "apply",
          "variants",
          "responsive",
          "screen",
          "layer",
          "import",
          "plugin",
          "source",
          "custom-variant",
          "theme",
        ],
      },
    ],
    "custom-property-pattern": null,
    "import-notation": null,
    "function-no-unknown": [true, {ignoreFunctions: ["theme"]}],
    "selector-class-pattern": null,
    "declaration-block-no-redundant-longhand-properties": null,
  },
  ignoreFiles: [".next/**", "dist/**", "coverage/**", "node_modules/**"],
};

export default config;
