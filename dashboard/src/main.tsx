import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { App } from "./App"
import "./styles.css"

const mount = document.getElementById("root")!
const viewportNodes = [document.documentElement, document.body, mount]

for (const node of viewportNodes) {
  node.style.backgroundColor = "#0b0b0e"
  node.style.minHeight = "100vh"
}
for (const node of [document.body, mount]) {
  node.style.display = "flex"
  node.style.flex = "1 0 auto"
  node.style.flexDirection = "column"
}

createRoot(mount).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
