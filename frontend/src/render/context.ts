import type { TemperatureUnit } from "../format";
import type { ActionCall } from "../logic";
import type { FrontendLocale, Localize } from "../types";

/**
 * What the shared templates need from the card that renders them: display
 * preferences, and the card's own way to open more-info and call actions,
 * so a failed action is reported by the card whose control was used.
 */
export interface RenderContext {
  unit: TemperatureUnit;
  locale: FrontendLocale | undefined;
  localize: Localize | undefined;
  moreInfo(entityId: string): void;
  call(action: ActionCall | null): void;
}
