/** Etiquetas humanas: el contrato interno con el backend permanece en inglés. */
export function verdictLabel(verdict?: string): string {
  switch (verdict) {
    case "APPROVE":
      return "APROBADO";
    case "ESCALATE":
      return "REQUIERE APROBACIÓN";
    case "REJECT":
      return "RECHAZADO";
    default:
      return "SIN VEREDICTO";
  }
}

export function auditTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    mandate_created: "mandato creado",
    verification: "verificación",
    revocation: "revocación",
    purchase_completed: "compra completada",
    agent_run: "corrida del agente",
  };
  return labels[type] ?? type.replace(/_/g, " ");
}

export function saturdayStateLabel(state: string): string {
  const labels: Record<string, string> = {
    idle: "EN ESPERA",
    thinking: "ANALIZANDO",
    approve: "APROBADO",
    escalate: "REQUIERE APROBACIÓN",
    reject: "RECHAZADO",
  };
  return labels[state] ?? state;
}

/** Convierte identificadores de dominio en nombres legibles, incluso dentro de textos. */
export function displayName(value: string): string {
  const exactLabels: Record<string, string> = {
    "travel.flights": "Vuelos",
    "travel.hotels": "Hoteles",
    "subscriptions": "Suscripciones",
    "digital.subscriptions": "Suscripciones",
    "mch_vuelaya": "VuelaYa",
  };
  if (exactLabels[value]) return exactLabels[value];
  if (/^fly_vy_\d+$/.test(value)) return `Vuelo ${Number(value.slice(-3))}`;
  if (value.startsWith("mch_")) return value.slice(4).replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (value.startsWith("travel.")) return value.slice(7).replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (value.startsWith("mnd_")) return `Mandato ${value.slice(4).replace(/_/g, " ")}`;

  let readable = value;
  for (const [technical, label] of Object.entries(exactLabels)) {
    readable = readable.replace(new RegExp(technical.replace(".", "\\."), "g"), label);
  }
  return readable
    .replace(/fly_vy_(\d+)/g, (_, number: string) => `Vuelo ${Number(number)}`)
    .replace(/travel\.([a-z_]+)/g, (_, category: string) => category.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()))
    .replace(/mch_([a-z_]+)/g, (_, merchant: string) => merchant.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()));
}

export function localizedText(value: string): string {
  return displayName(value)
    .replace(/\bAPPROVE\b/g, verdictLabel("APPROVE"))
    .replace(/\bESCALATE\b/g, verdictLabel("ESCALATE"))
    .replace(/\bREJECT\b/g, verdictLabel("REJECT"));
}

/** Ajusta la redacción de los checks sin alterar el valor técnico que entregó el motor. */
export function checkDetailLabel(rule: string, detail: string): string {
  if (rule === "category") {
    const technicalCategory = detail.split(" ")[0];
    const category = displayName(technicalCategory);
    const feminine = category === "Suscripciones";
    if (detail.includes("permitida")) return `${category} ${feminine ? "permitidas" : "permitidos"}`;
    if (detail.includes("no está")) return `${category} no está entre las categorías permitidas`;
  }
  if (rule === "merchant") {
    const technicalMerchant = detail.split(" ")[0];
    const merchant = displayName(technicalMerchant);
    if (detail.includes("permitido")) return `${merchant} autorizado`;
    if (detail.includes("no está")) return `${merchant} no está entre los comercios autorizados`;
  }
  return localizedText(detail);
}

export function checkRuleLabel(rule: string): string {
  const labels: Record<string, string> = {
    mandate_exists: "Existencia del mandato",
    signature: "Firma",
    agent_identity: "Identidad del agente",
    status: "Estado del mandato",
    amount: "Monto",
    category: "Categoría",
    merchant: "Comercio",
    uses: "Usos disponibles",
    "condition.price_below": "Condición de precio",
    "engine.internal_error": "Error del motor",
  };
  return labels[rule] ?? displayName(rule);
}
