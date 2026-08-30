import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

def enviar_ticket_confirmacion(correo_destino: str, detalles_reserva: dict) -> dict:
    """
    Envía el recibo final al usuario una vez que el Semantic Firewall 
    aprobó y Stripe procesó el cobro exitosamente.
    """
    dest = correo_destino.strip() if correo_destino else (SMTP_USER or "user@example.com")
    if not dest or "@" not in dest:
        dest = SMTP_USER or "user@example.com"

    msg = MIMEMultipart()
    pnr = detalles_reserva.get('pnr', 'PNR-VYA-849201')
    msg['Subject'] = f"✈️ Tu compra autónoma fue exitosa - Aegis Zero-Trust [{pnr}]"
    msg['From'] = SMTP_USER or "aegis@zero-trust.protocol"
    msg['To'] = dest
    
    destino = detalles_reserva.get('destino') or detalles_reserva.get('route') or 'Vuelo VuelaYa'
    proveedor = detalles_reserva.get('proveedor') or detalles_reserva.get('merchant') or 'VuelaYa Travel'
    precio = detalles_reserva.get('precio_total') or detalles_reserva.get('price') or 130
    moneda = detalles_reserva.get('moneda') or 'USD'

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; background-color: #f8fafc; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: #ffffff; border: 1px solid #e2e8f0; padding: 24px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
            <div style="border-bottom: 2px solid #0056b3; padding-bottom: 12px; margin-bottom: 16px;">
              <h2 style="color: #0056b3; margin: 0;">Aegis: Misión Cumplida 🛡️</h2>
              <p style="color: #64748b; font-size: 14px; margin: 4px 0 0;">Protocolo de Comercio Agéntico Zero-Trust</p>
            </div>
            
            <p>Hola,</p>
            <p>Tu agente autónomo <strong>Saturday</strong> encontró una oferta que cumple estrictamente con tu mandato y ha completado la compra de forma segura mientras estabas <em>off-session</em>.</p>
            
            <div style="background-color: #f1f5f9; border-radius: 8px; padding: 16px; margin: 20px 0;">
              <h3 style="color: #1e293b; margin-top: 0; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; font-size: 16px;">Detalles de la Reserva</h3>
              <ul style="list-style: none; padding-left: 0; margin: 0; line-height: 1.8;">
                  <li><strong>Destino / Ruta:</strong> {destino}</li>
                  <li><strong>Proveedor:</strong> {proveedor}</li>
                  <li><strong>Código de Reserva (PNR):</strong> <span style="background: #dbeafe; color: #1e40af; padding: 3px 8px; border-radius: 4px; font-family: monospace; font-weight: bold;">{pnr}</span></li>
                  <li><strong>Total Cobrado:</strong> <span style="color: #16a34a; font-weight: bold;">${precio} {moneda}</span></li>
              </ul>
            </div>
            
            <p style="font-size: 14px; color: #475569;">
              ✅ <strong>Auditoría Criptográfica:</strong> La verificación formal confirmó que esta compra respetó tu límite de presupuesto, no contenía cargos ocultos y fue sellada con Ed25519.
            </p>
            <br>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 16px 0;">
            <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">
              Mensaje automático de tu sistema Zero-Trust. El token de pago de un solo uso (Scoped Virtual Token) ha sido rotado.
            </p>
        </div>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    
    if SMTP_USER and SMTP_PASS:
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            print(f"📧 Ticket de confirmación enviado exitosamente a {dest}")
            return {"status": 200, "mensaje": "Ticket enviado con éxito al usuario.", "enviado_a": dest}
        except Exception as e:
            print(f"Aviso SMTP al enviar ticket a {dest}: {e}")
            return {"status": 500, "mensaje": f"Fallo envío de ticket por SMTP: {e}", "enviado_a": dest}
    
    print(f"📧 [Modo Local] Ticket de confirmación simulado para {dest} (PNR: {pnr})")
    return {"status": 200, "mensaje": "Ticket generado en modo local.", "enviado_a": dest}