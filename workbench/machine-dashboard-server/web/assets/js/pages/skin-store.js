import { getSkins, getCurrentSkinId, setSkin } from "../shared/skin.js";

export async function mount(root) {
  const list = root.querySelector("#skin-list");
  const render = () => {
    const current = getCurrentSkinId();
    list.innerHTML = getSkins().map(skin => `<article class="skin-card card ${skin.className}" data-ui-id="skin-store.card.${skin.id}"><div class="skin-preview"><i></i><i></i><i></i></div><div class="skin-card-body"><h2>${skin.name}</h2><p>${skin.description}</p><button type="button" class="${current === skin.id ? "" : "primary"}" data-skin-id="${skin.id}" ${current === skin.id ? "disabled" : ""}>${current === skin.id ? "使用中" : "使用皮肤"}</button></div></article>`).join("");
  };
  list.addEventListener("click", event => { const button = event.target.closest("[data-skin-id]"); if (!button) return; setSkin(button.dataset.skinId); render(); });
  render();
}
export function unmount() {}
