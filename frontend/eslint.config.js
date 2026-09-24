import js from "@eslint/js";
import lit from "eslint-plugin-lit";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  lit.configs["flat/recommended"],
  {
    files: ["src/**/*.ts", "test/**/*.ts"],
    rules: {
      // A class field with the same name as a reactive property replaces
      // Lit's generated accessor, so the element never re-renders when the
      // value changes. This is how the card got stuck in its loading state.
      "lit/no-classfield-shadowing": "error",
      "lit/lifecycle-super": "error",
      "lit/no-native-attributes": "error",
      "lit/no-this-assign-in-render": "error",
      "lit/no-useless-template-literals": "error",
    },
  },
  {
    files: ["*.js", "*.mjs"],
    languageOptions: { globals: { console: "readonly", process: "readonly" } },
  },
);
