import type { FrontendLocale, UnitSystem } from "./types";

/**
 * The snapshot carries degrees Celsius only. The card converts once, for
 * display and for the value it sends back, to the user's unit system.
 */
export type TemperatureUnit = "°C" | "°F";

export const CELSIUS: TemperatureUnit = "°C";

/** Target bounds enforced by the card, in degrees Celsius. */
export const TARGET_MIN_CELSIUS = 5;
export const TARGET_MAX_CELSIUS = 35;

export function temperatureUnit(unitSystem: UnitSystem | undefined): TemperatureUnit {
  return unitSystem?.temperature === "°F" ? "°F" : CELSIUS;
}

export function toDisplayTemperature(celsius: number, unit: TemperatureUnit): number {
  return unit === "°F" ? (celsius * 9) / 5 + 32 : celsius;
}

/** Convert a temperature difference, which has no offset. */
export function toDisplayDelta(celsiusDelta: number, unit: TemperatureUnit): number {
  return unit === "°F" ? (celsiusDelta * 9) / 5 : celsiusDelta;
}

/** The target step of the card's plus and minus buttons, in the display unit. */
export function targetStep(unit: TemperatureUnit): number {
  return unit === "°F" ? 1 : 0.5;
}

/**
 * Move a Celsius target one step in the display unit.
 *
 * The result is in the display unit, snapped to the step grid and bounded,
 * because Home Assistant interprets `climate.set_temperature` in the user's
 * unit system.
 */
export function steppedTarget(celsius: number, direction: 1 | -1, unit: TemperatureUnit): number {
  const step = targetStep(unit);
  const current = toDisplayTemperature(celsius, unit);
  // Move to the next grid value in the chosen direction, so an off-grid value
  // such as 69.8 °F becomes 70 or 69. The epsilon absorbs conversion noise.
  const units = current / step;
  const snapped = (direction > 0 ? Math.floor(units + 1e-9) + 1 : Math.ceil(units - 1e-9) - 1) * step;
  const minimum = toDisplayTemperature(TARGET_MIN_CELSIUS, unit);
  const maximum = toDisplayTemperature(TARGET_MAX_CELSIUS, unit);
  return Number(Math.min(maximum, Math.max(minimum, snapped)).toFixed(1));
}

/**
 * Resolve the locale for number formatting the way the Home Assistant
 * frontend does for the user's number format profile setting.
 */
export function numberLocale(locale: FrontendLocale | undefined): string | string[] | undefined {
  switch (locale?.number_format) {
    case "comma_decimal":
      return ["en-US", "en"];
    case "decimal_comma":
      return ["de", "es", "it"];
    case "space_comma":
      return ["fr", "sv", "cs"];
    case "quote_decimal":
      return ["de-CH"];
    case "system":
      return undefined;
    case "none":
      return "en-US";
    default:
      return locale?.language;
  }
}

const formatters = new Map<string, Intl.NumberFormat>();

export function formatNumber(value: number, locale: FrontendLocale | undefined, fractionDigits = 1): string {
  const resolved = numberLocale(locale);
  const useGrouping = locale?.number_format !== "none";
  const key = `${JSON.stringify(resolved)}|${fractionDigits}|${useGrouping}`;
  let formatter = formatters.get(key);
  if (!formatter) {
    try {
      formatter = new Intl.NumberFormat(resolved, {
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
        useGrouping,
      });
    } catch {
      formatter = new Intl.NumberFormat(undefined, {
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
      });
    }
    formatters.set(key, formatter);
  }
  return formatter.format(value);
}

export function formatTemperature(celsius: number, unit: TemperatureUnit, locale: FrontendLocale | undefined): string {
  return formatNumber(toDisplayTemperature(celsius, unit), locale);
}

export function formatTemperatureDelta(celsiusDelta: number, unit: TemperatureUnit, locale: FrontendLocale | undefined): string {
  return formatNumber(toDisplayDelta(celsiusDelta, unit), locale);
}
