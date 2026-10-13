import React from "react";
import ReactDOM from "react-dom/client";
const root = ReactDOM.createRoot(document.getElementById("root")!);
if (new URLSearchParams(location.search).get("view") === "tasks") {
  void Promise.all([import("./App"), import("./styles.css")]).then(([{ default: App }]) =>
    root.render(<React.StrictMode><App /></React.StrictMode>));
} else {
  void Promise.all([import("../../../../jarvis-main/src/App"), import("../../../../jarvis-main/src/index.css")])
    .then(([{ default: App }]) => root.render(<App />));
}
