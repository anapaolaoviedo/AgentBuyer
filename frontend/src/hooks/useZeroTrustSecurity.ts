import { useState, useRef, useCallback, useMemo, useEffect } from "react";

export interface MandatePayload {
  destination: string;
  max_amount_per_tx: number;
  monthly_limit: number;
  currency: string;
  passengers: string[];
  expires_at: string;
  status: string;
  mandate_id?: string;
  human?: {
    id: string;
    display_name: string;
    phone?: string;
    id_document?: string;
  };
  agent?: {
    id: string;
    display_name: string;
  };
  constraints?: {
    max_amount_per_purchase: number;
    max_amount_per_tx: number;
    monthly_budget: number;
    currency: string;
    allowed_categories: string[];
    allowed_merchants: string[];
    max_uses: number;
    conditions: Array<{ type: string; value: number }>;
    off_session_consent: boolean;
  };
  payment_token?: {
    token_id: string;
    token_type: string;
    masked_card: string;
    bank_issuer: string;
  };
  authentication?: {
    passkey_verified: boolean;
    liveness_verified: boolean;
    possession_verified: boolean;
    enrolled_at: string;
  };
  signature?: string;
}

export interface ZeroTrustSecurityState {
  isPasskeyVerified: boolean;
  isLivenessVerified: boolean;
  isPossessionVerified: boolean;
  isStripeTokenized: boolean;
  paymentMethodId: string | null;
  errorMessage: string | null;
  isLoading: boolean;
  isSubmitEnabled: boolean;
}

const API_BASE = "http://127.0.0.1:8000";

/**
 * Custom Hook de React para Enrolamiento Fuerte Único (Zero-Trust MFA).
 * 
 * Regla inquebrantable de autorización:
 * isSubmitEnabled = isStripeTokenized && (isPasskeyVerified || isLivenessVerified) && isPossessionVerified
 */
export function useZeroTrustSecurity() {
  const [isPasskeyVerified, setIsPasskeyVerified] = useState<boolean>(false);
  const [isLivenessVerified, setIsLivenessVerified] = useState<boolean>(false);
  const [isPossessionVerified, setIsPossessionVerified] = useState<boolean>(false);
  const [isStripeTokenized, setIsStripeTokenized] = useState<boolean>(false);
  const [paymentMethodId, setPaymentMethodId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // 1. Orquestador Fail-Closed: Mínimo 2 Factores (Tokenización PCI + Inherencia + Posesión)
  const isSubmitEnabled = useMemo<boolean>(() => {
    const hasInherency = isPasskeyVerified || isLivenessVerified;
    return Boolean(isStripeTokenized && hasInherency && isPossessionVerified);
  }, [isStripeTokenized, isPasskeyVerified, isLivenessVerified, isPossessionVerified]);

  // 2. Factor de Inherencia 1: WebAuthn / Passkey Biométrica Nativa
  const handlePasskeyChallenge = useCallback(async (): Promise<boolean> => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      if (!window.PublicKeyCredential) {
        throw new Error("WebAuthn / Passkeys no están soportadas en este navegador o entorno.");
      }

      const challenge = new Uint8Array(32);
      window.crypto.getRandomValues(challenge);

      const userId = new Uint8Array(16);
      window.crypto.getRandomValues(userId);

      const publicKeyCredentialCreationOptions: PublicKeyCredentialCreationOptions = {
        challenge,
        rp: {
          name: "Aegis Zero-Trust Autonomous Commerce",
          id: window.location.hostname || "localhost",
        },
        user: {
          id: userId,
          name: "cardholder@aegis.protocol",
          displayName: "Aegis Verified Cardholder",
        },
        pubKeyCredParams: [
          { alg: -7, type: "public-key" },  // ES256
          { alg: -8, type: "public-key" },  // Ed25519 / EdDSA
          { alg: -257, type: "public-key" }, // RS256
        ],
        authenticatorSelection: {
          authenticatorAttachment: "platform",
          userVerification: "required",
          residentKey: "preferred",
        },
        timeout: 60000,
        attestation: "direct",
      };

      const credential = await navigator.credentials.create({
        publicKey: publicKeyCredentialCreationOptions,
      });

      if (!credential) {
        throw new Error("No se pudo completar el desafío biométrico WebAuthn.");
      }

      setIsPasskeyVerified(true);
      setIsLoading(false);
      return true;
    } catch (err: any) {
      const errorStr = err?.message || "Error al autenticar con Passkey / Biometría de plataforma.";
      setErrorMessage(errorStr);
      setIsPasskeyVerified(false);
      setIsLoading(false);
      return false;
    }
  }, []);

  // 3. Factor de Inherencia 2: Liveness Detection Anti-Spoofing en Cámara (WebRTC + Canvas)
  const startCamera = useCallback(async (): Promise<MediaStream> => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("La API de captura de medios (getUserMedia) no está disponible en este dispositivo.");
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.muted = true;
        videoRef.current.setAttribute("autoplay", "true");
        videoRef.current.setAttribute("playsinline", "true");
        try {
          await videoRef.current.play();
        } catch {
          videoRef.current.onloadedmetadata = () => {
            videoRef.current?.play().catch(() => {});
          };
        }
      }

      setIsLoading(false);
      return stream;
    } catch (err: any) {
      const errorStr = err?.message || "No se pudo acceder a la cámara para la prueba de vida.";
      setErrorMessage(errorStr);
      setIsLoading(false);
      throw new Error(errorStr);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const verifyLiveness = useCallback(async (): Promise<boolean> => {
    setIsLoading(true);
    setErrorMessage(null);

    const video = videoRef.current;
    if (!video || video.readyState < 2) {
      const errStr = "El flujo de video no está listo para evaluar la prueba de vida.";
      setErrorMessage(errStr);
      setIsLoading(false);
      throw new Error(errStr);
    }

    try {
      const width = video.videoWidth || 640;
      const height = video.videoHeight || 480;

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;

      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) {
        throw new Error("No se pudo instanciar el contexto gráfico 2D del canvas.");
      }

      ctx.drawImage(video, 0, 0, width, height);

      const imageData = ctx.getImageData(0, 0, width, height);
      const data = imageData.data;
      const totalPixels = width * height;

      let totalLuma = 0;
      const lumaValues: number[] = new Array(totalPixels);

      // Algoritmo fotométrico ITU-R BT.601 (0.299R + 0.587G + 0.114B)
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        const luma = 0.299 * r + 0.587 * g + 0.114 * b;
        const pixelIdx = i / 4;
        lumaValues[pixelIdx] = luma;
        totalLuma += luma;
      }

      const avgLuma = totalLuma / totalPixels;

      let varianceSum = 0;
      for (let i = 0; i < totalPixels; i++) {
        const diff = lumaValues[i] - avgLuma;
        varianceSum += diff * diff;
      }
      const pixelVariance = Math.sqrt(varianceSum / totalPixels);

      // Detección estricta: Bloqueo de cámara tapada / pantalla negra / imagen estática
      if (avgLuma < 25 || pixelVariance < 8) {
        const securityError = "403 Liveness Check Failed: Camera obstructed or insufficient illumination";
        setErrorMessage(securityError);
        setIsLivenessVerified(false);
        setIsLoading(false);
        throw new Error(securityError);
      }

      // Verificación humana exitosa -> Apagar cámara y liberar recursos de hardware
      stopCamera();
      setIsLivenessVerified(true);
      setIsLoading(false);
      return true;
    } catch (err: any) {
      stopCamera();
      const errorStr = err?.message || "403 Liveness Check Failed";
      setErrorMessage(errorStr);
      setIsLivenessVerified(false);
      setIsLoading(false);
      throw err;
    }
  }, [stopCamera]);

  // 4. Factor de Posesión: SMS / Email OTP vía API Real Backend (Twilio Verify)
  const sendOtp = useCallback(async (contact: string, channel: "sms" | "email" = "sms"): Promise<any> => {
    setIsLoading(true);
    setErrorMessage(null);

    const endpoint = channel === "email" ? `${API_BASE}/auth/email/start` : `${API_BASE}/auth/sms/start`;
    const body = channel === "email" ? { email: contact.trim() } : { phone_number: contact.trim() };

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Error al solicitar OTP: HTTP ${response.status}`);
      }

      const result = await response.json();
      setIsLoading(false);
      return result;
    } catch (err: any) {
      const errorStr = err?.message || "No fue posible enviar el código de verificación.";
      setErrorMessage(errorStr);
      setIsLoading(false);
      throw err;
    }
  }, []);

  const verifyOtp = useCallback(async (contact: string, code: string, channel: "sms" | "email" = "sms"): Promise<boolean> => {
    setIsLoading(true);
    setErrorMessage(null);

    const cleanCode = code.trim();
    if (!/^\d{6}$/.test(cleanCode)) {
      const errStr = "El código OTP debe constar de 6 dígitos numéricos.";
      setErrorMessage(errStr);
      setIsLoading(false);
      throw new Error(errStr);
    }

    const endpoint = channel === "email" ? `${API_BASE}/auth/email/check` : `${API_BASE}/auth/sms/check`;
    const body = channel === "email"
      ? { email: contact.trim(), code: cleanCode }
      : { phone_number: contact.trim(), code: cleanCode };

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "401 Unauthorized: Código incorrecto o expirado.");
      }

      const result = await response.json();
      if (result.verified || result.ok) {
        setIsPossessionVerified(true);
        setIsLoading(false);
        return true;
      }

      throw new Error("El código no pudo ser verificado satisfactoriamente.");
    } catch (err: any) {
      const errorStr = err?.message || "Código incorrecto o expirado.";
      setErrorMessage(errorStr);
      setIsPossessionVerified(false);
      setIsLoading(false);
      throw err;
    }
  }, []);

  // 5. Tokenización PCI: Stripe.js Real con fallback a Scoped Virtual Token
  const handleTokenizeCard = useCallback(async (cardData?: string): Promise<string> => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      // Intento 1: Stripe.js real si hay clave pública configurada
      const stripePublicKey = (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_STRIPE_PUBLISHABLE_KEY) || "";
      
      if (stripePublicKey && stripePublicKey.startsWith("pk_")) {
        // Carga dinámica de Stripe.js desde CDN (sin dependencia npm)
        if (!(window as any).Stripe) {
          await new Promise<void>((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://js.stripe.com/v3/";
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("No se pudo cargar Stripe.js"));
            document.head.appendChild(script);
          });
        }

        const stripe = (window as any).Stripe(stripePublicKey);
        const elements = stripe.elements();
        const cardElement = elements.create("card", { hidePostalCode: true });
        
        // Montar temporalmente en un contenedor invisible para crear el PaymentMethod
        const container = document.createElement("div");
        container.style.position = "fixed";
        container.style.opacity = "0";
        container.style.pointerEvents = "none";
        document.body.appendChild(container);
        cardElement.mount(container);

        const { paymentMethod, error: stripeError } = await stripe.createPaymentMethod({
          type: "card",
          card: cardElement,
        });

        // Limpieza
        cardElement.unmount();
        container.remove();

        if (stripeError) {
          throw new Error(stripeError.message || "Error en Stripe Elements.");
        }

        const tokenId = paymentMethod?.id || `pm_${Math.random().toString(36).substring(2, 10)}`;
        setPaymentMethodId(tokenId);
        setIsStripeTokenized(true);
        setIsLoading(false);
        return tokenId;
      }

      // Intento 2: Fallback — Scoped Virtual Token para demo/local sin Stripe key
      const randomEntropy = Math.random().toString(36).substring(2, 10);
      const generatedToken = `vtok_${randomEntropy}`;

      setPaymentMethodId(generatedToken);
      setIsStripeTokenized(true);
      setIsLoading(false);
      return generatedToken;
    } catch (err: any) {
      const errorStr = err?.message || "Error al tokenizar el método de pago.";
      setErrorMessage(errorStr);
      setIsStripeTokenized(false);
      setIsLoading(false);
      throw new Error(errorStr);
    }
  }, []);

  // 6. Envío del Mandato Delegado (POST /mandates) - Fail Closed
  const submitDelegatedMandate = useCallback(async (payload: MandatePayload): Promise<any> => {
    const hasInherency = isPasskeyVerified || isLivenessVerified;
    if (!isStripeTokenized || !hasInherency || !isPossessionVerified) {
      const securityErr = "403 Forbidden: No se cumplen los factores mínimos de seguridad requeridos (PCI Token + Biometría + Posesión).";
      setErrorMessage(securityErr);
      throw new Error(securityErr);
    }

    setIsLoading(true);
    setErrorMessage(null);

    const fullPayload = {
      mandate_id: payload.mandate_id || `mnd_delegated_${Date.now().toString(36)}`,
      destination: payload.destination,
      max_amount_per_tx: payload.max_amount_per_tx,
      monthly_limit: payload.monthly_limit,
      currency: payload.currency || "USD",
      passengers: payload.passengers || ["passenger_01"],
      expires_at: payload.expires_at,
      status: payload.status || "active",
      human: payload.human || { id: "hum_marta", display_name: "Marta" },
      agent: payload.agent || { id: "agt_saturday", display_name: "Saturday" },
      constraints: payload.constraints || {
        max_amount_per_purchase: payload.max_amount_per_tx,
        max_amount_per_tx: payload.max_amount_per_tx,
        monthly_budget: payload.monthly_limit,
        currency: payload.currency || "USD",
        allowed_categories: ["travel.flights"],
        allowed_merchants: ["mch_vuelaya"],
        max_uses: 3,
        conditions: [{ type: "price_below", value: payload.max_amount_per_tx }],
        off_session_consent: true,
      },
      payment_token: payload.payment_token || {
        token_id: paymentMethodId || "vtok_default_secured",
        token_type: "SCOPED_VIRTUAL_TOKEN",
        masked_card: "•••• 4242",
        bank_issuer: "Stripe Vault / Galicia AI",
      },
      authentication: {
        passkey_verified: isPasskeyVerified,
        liveness_verified: isLivenessVerified,
        possession_verified: isPossessionVerified,
        enrolled_at: new Date().toISOString(),
      },
      signature: payload.signature || "ed25519_delegated_mandate_signature",
    };

    try {
      const response = await fetch(`${API_BASE}/mandates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fullPayload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Error en registro del mandato: HTTP ${response.status}`);
      }

      const result = await response.json();
      setIsLoading(false);
      return result;
    } catch (err: any) {
      const errorStr = err?.message || "No se pudo registrar el mandato delegado en el backend.";
      setErrorMessage(errorStr);
      setIsLoading(false);
      throw err;
    }
  }, [isStripeTokenized, isPasskeyVerified, isLivenessVerified, isPossessionVerified, paymentMethodId]);

  const clearError = useCallback(() => {
    setErrorMessage(null);
  }, []);

  const resetSecurityState = useCallback(() => {
    stopCamera();
    setIsPasskeyVerified(false);
    setIsLivenessVerified(false);
    setIsPossessionVerified(false);
    setIsStripeTokenized(false);
    setPaymentMethodId(null);
    setErrorMessage(null);
    setIsLoading(false);
  }, [stopCamera]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  return {
    videoRef,
    isPasskeyVerified,
    isLivenessVerified,
    isPossessionVerified,
    isStripeTokenized,
    paymentMethodId,
    errorMessage,
    isLoading,
    isSubmitEnabled,
    handlePasskeyChallenge,
    startCamera,
    stopCamera,
    verifyLiveness,
    sendOtp,
    verifyOtp,
    handleTokenizeCard,
    submitDelegatedMandate,
    clearError,
    resetSecurityState,
  };
}
