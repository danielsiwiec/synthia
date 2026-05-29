import { renderMermaidSVG, THEMES } from "beautiful-mermaid";

const themeName = process.env.MERMAID_THEME || "github-light";
const theme = THEMES[themeName] ?? THEMES["github-light"];

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  try {
    process.stdout.write(renderMermaidSVG(input, theme));
  } catch (error) {
    process.stderr.write(String(error?.stack ?? error));
    process.exit(1);
  }
});
