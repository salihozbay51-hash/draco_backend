import tr from "./locales/tr";
import en from "./locales/en";
import ru from "./locales/ru";
import de from "./locales/de";
import vi from "./locales/vi";

export const messages = { tr, en, ru, de, vi };

export const languageOptions = [
  { code: "tr", label: "Türkçe", flag: "🇹🇷" },
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "ru", label: "Русский", flag: "🇷🇺" },
  { code: "de", label: "Deutsch", flag: "🇩🇪" },
  { code: "vi", label: "Tiếng Việt", flag: "🇻🇳" },
];

export function getSavedLanguage() {
  return localStorage.getItem("lang") || "tr";
}

export function saveLanguage(lang) {
  localStorage.setItem("lang", lang);
}

export function translate(lang, key) {
  return messages[lang]?.[key] || messages.tr[key] || key;
}