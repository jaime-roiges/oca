/** @odoo-module **/

// Odoo 20's product page updates the price when a variant or quantity changes.
// Keep the contract-only two-line layout synchronized with the same RPC data.
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductPage } from "@website_sale/interactions/product_page";

patch(ProductPage.prototype, {
    async _onChangeCombination(ev, parent, combination, attributeValueImages) {
        const result = await super._onChangeCombination(
            ev, parent, combination, attributeValueImages
        );
        const container = parent.querySelector('[name="product_price_container"]');
        if (container) {
            if (combination.tl_contract_offer && !combination.hide_price) {
                container.dataset.tlContractOffer = "1";
            } else {
                delete container.dataset.tlContractOffer;
            }
        }
        // Availability belongs to the selected variant, never to a template
        // with an arbitrary variant. Use textContent for all server values.
        const availability = parent.querySelector('[data-tl-contract-availability]');
        if (availability) {
            const contracts = combination.tl_contract_availabilities || [];
            availability.classList.toggle('d-none', !contracts.length);
            const list = availability.querySelector('[data-tl-contract-list]');
            if (list) {
                list.replaceChildren();
                for (const contract of contracts) {
                    const row = document.createElement('li');
                    row.className = 'd-flex justify-content-between gap-3 py-1';
                    const id = Number(contract.id);
                    const canBuy = Number(contract.quantity) > 0 &&
                        Number.isSafeInteger(id) && id > 0;
                    const name = document.createElement(canBuy ? 'a' : 'span');
                    name.textContent = contract.contract_name || '';
                    if (canBuy) {
                        name.href = `/shop/blanket/contract/${id}`;
                    }
                    const headline = document.createElement('div');
                    headline.className = 'd-flex justify-content-between gap-3';
                    const qty = document.createElement('span');
                    qty.className = 'text-nowrap fw-semibold';
                    qty.textContent = `${contract.quantity_display} ${contract.uom_name}`;
                    headline.append(name, qty);
                    row.className = 'py-2 border-bottom';
                    row.append(headline);
                    if (contract.is_packaging) {
                        const subtitle = document.createElement('small');
                        subtitle.className = 'text-muted d-block mt-1';
                        subtitle.textContent = `${contract.full_packages_display} ` +
                            `${contract.selected_uom_name} ${_t("complete packages")} ` +
                            `(1 = ${contract.package_size_display} ${contract.main_uom_name}); ` +
                            `${_t("remainder:")} ${contract.leftover_base_display} ${contract.main_uom_name}`;
                        row.append(subtitle);
                    } else if (contract.show_equivalent) {
                        const subtitle = document.createElement('small');
                        subtitle.className = 'text-muted d-block mt-1';
                        subtitle.textContent = `${_t("Equivalent:")} ${contract.available_selected_display} ` +
                            `${contract.selected_uom_name}`;
                        row.append(subtitle);
                    }
                    list.append(row);
                }
            }
        }
        return result;
    },
});
