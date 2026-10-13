import { globalIgnores } from "eslint/config";
import nextPlugin from "@next/eslint-plugin-next";

export default [{
  plugins: { "@next/next": nextPlugin },
  rules: nextPlugin.configs.recommended.rules,
}, globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"])];
