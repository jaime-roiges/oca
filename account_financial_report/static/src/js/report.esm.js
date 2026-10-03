function toTitleCase(str) {
    return str
        .replaceAll(".", " ")
        .replace(
            /\w\S*/g,
            (txt) => `${txt.charAt(0).toUpperCase()}${txt.substr(1).toLowerCase()}`
        );
}

/**
 * Enrich an HTML report iframe with links that open records matching the
 * domain declared by the report template.
 *
 * Odoo 20's ReportAction no longer exposes an iframe useRef. The iframe is
 * provided by ReportAction.onIframeLoaded(ev), so callers must pass the
 * iframe element received through ev.currentTarget.
 *
 * @param {import("@odoo/owl").Component} component
 * @param {HTMLIFrameElement} iframe
 * @param {String|null} selector
 */
export function enrichWithActionLinks(component, iframe, selector = null) {
    const contentDocument = iframe?.contentDocument;
    if (!contentDocument) {
        return;
    }

    const targets = selector
        ? [...contentDocument.querySelectorAll(selector)]
        : [contentDocument];

    for (const currentTarget of targets) {
        const elementsToWrap = currentTarget.querySelectorAll("[res-model][domain]");
        for (const element of elementsToWrap) {
            // Avoid wrapping the same node twice if another customization invokes
            // onIframeLoaded more than once for the same document.
            if (element.parentElement?.dataset?.afrActionLink === "1") {
                continue;
            }
            const wrapper = contentDocument.createElement("a");
            wrapper.href = "#";
            wrapper.dataset.afrActionLink = "1";
            wrapper.addEventListener("click", (ev) => {
                ev.preventDefault();
                component.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: element.getAttribute("res-model"),
                    domain: element.getAttribute("domain"),
                    name: toTitleCase(element.getAttribute("res-model")),
                    views: [
                        [false, "list"],
                        [false, "form"],
                    ],
                });
            });
            element.parentNode.insertBefore(wrapper, element);
            wrapper.appendChild(element);
        }
    }
}
