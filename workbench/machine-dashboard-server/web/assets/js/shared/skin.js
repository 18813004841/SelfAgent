const STORAGE_KEY = "workbench.skin.id";
const skins = [
  { id: "default", name: "清新工作台", description: "当前浅色绿系工作台风格。", className: "skin-default" },
  { id: "sunset", name: "暖橙模块", description: "保留卡片结构，使用暖橙色强调。", className: "skin-sunset" },
  { id: "mist", name: "雾光工作台", description: "参考个人工作台效果图的雾白蓝灰与新拟态高光。", className: "skin-mist" },
  { id: "cozy", name: "暖日手账", description: "奶油纸感、蜜桃粉与温柔植物色。", className: "skin-cozy" },
  { id: "vintage", name: "复古工坊", description: "旧纸、炭黑与砖红的工业档案风格。", className: "skin-vintage" },
  { id: "cosmos", name: "星际霓光", description: "深空蓝底色，点缀青紫霓虹光。", className: "skin-cosmos" },
  { id: "playful", name: "缤纷创意", description: "明亮蓝色与活泼彩色的创意工作台。", className: "skin-playful" },
  { id: "glass", name: "云彩琉璃", description: "淡紫蓝渐变与轻盈的磨砂玻璃质感。", className: "skin-glass" },
  { id: "gold", name: "曜石鎏金", description: "沉静黑色与暖金线条的商务风格。", className: "skin-gold" },
  { id: "ink", name: "水墨雅集", description: "宣纸、山水、竹影与印章红的东方工作台风格。", className: "skin-ink" },
];
export function getSkins() { return skins.slice(); }
export function getCurrentSkinId() { try { return skins.some(s => s.id === localStorage.getItem(STORAGE_KEY)) ? localStorage.getItem(STORAGE_KEY) : "default"; } catch { return "default"; } }
export function applySkin(id = getCurrentSkinId()) { const skin = skins.find(item => item.id === id) || skins[0]; document.documentElement.dataset.skin = skin.id; return skin.id; }
export function setSkin(id) { const selected = skins.find(item => item.id === id) || skins[0]; try { localStorage.setItem(STORAGE_KEY, selected.id); } catch {} applySkin(selected.id); window.dispatchEvent(new CustomEvent("workbench:skin-changed", { detail: { id: selected.id } })); return selected; }
