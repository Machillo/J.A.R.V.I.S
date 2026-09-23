import { LockKeyhole, MailCheck, ShieldCheck } from "lucide-react";

const path = window.location.pathname;
const isPrivacy = path === "/privacy";
const isTerms = path === "/terms";
const isDeletion = path === "/delete-account";

function DeleteAccountPage() {
  return <>
    <span className="public-kicker">CONTROL DE TUS DATOS</span>
    <h1>Eliminar tu cuenta de DINCR</h1>
    <p className="public-lead">Podés solicitar la eliminación de tu cuenta y de los datos asociados desde la aplicación DINCR.</p>
    <section className="public-copy legal-copy">
      <h2>Cómo solicitarla</h2>
      <p>Ingresá a tu cuenta, abrí Perfil o Más → Ajustes de cuenta y plan → Eliminar cuenta, y confirmá la solicitud. Si ya no tenés acceso a tu cuenta, abrí la aplicación y usá la opción de soporte para pedir ayuda con la recuperación del acceso antes de eliminarla.</p>
      <p>Si necesitás ayuda, escribí a <a href="mailto:soporte@dincr.com">soporte@dincr.com</a>.</p>
      <h2>Qué se elimina</h2>
      <p>Se eliminan el perfil y los datos financieros asociados, incluidos movimientos, deudas, metas y configuraciones. Algunos registros pueden conservarse temporalmente cuando sea necesario por obligaciones legales, seguridad, pagos, copias de respaldo o reclamaciones, según la <a href="/privacy">Política de Privacidad</a>.</p>
    </section>
  </>;
}

function AboutPage() {
  return <>
    <span className="public-kicker">ASISTENTE FINANCIERO PERSONAL</span>
    <h1>DINCR</h1>
    <p className="public-lead">Herramientas para organizar ingresos, gastos, deudas, metas y decisiones financieras desde una experiencia privada y orientada a móvil.</p>
    <section className="public-feature-grid" aria-label="Funciones principales">
      <article><MailCheck size={24}/><h2>Control financiero</h2><p>Centraliza información que el usuario registra o autoriza para construir su panorama financiero.</p></article>
      <article><ShieldCheck size={24}/><h2>Decisiones del usuario</h2><p>Las proyecciones y sugerencias son informativas. El usuario conserva el control de sus decisiones y movimientos.</p></article>
      <article><LockKeyhole size={24}/><h2>Acceso protegido</h2><p>La información se separa por cuenta y se limita a servicios técnicos necesarios para operar la aplicación.</p></article>
    </section>
  </>;
}

function TermsPage() {
  return <>
    <span className="public-kicker">VERSIÓN 2026-09-23-v2 · VIGENTE DESDE EL 23 DE SEPTIEMBRE DE 2026</span>
    <h1>Términos y Condiciones</h1>
    <p className="public-lead">Estos términos regulan el acceso y uso de DINCR, servicio digital desarrollado y operado desde Costa Rica por Kenneth Andrés Alvarado Obando.</p>
    <section className="public-copy legal-copy">
      <h2>1. Aceptación y capacidad</h2><p>Al crear o utilizar una cuenta, la persona confirma que leyó y aceptó estos términos y la Política de Privacidad. Debe tener al menos 18 años y capacidad legal para contratar. Si no está de acuerdo, no debe utilizar el servicio.</p>
      <h2>2. Finalidad del servicio</h2><p>DINCR ayuda a registrar, organizar, analizar y proyectar información financiera. Sus cálculos, alertas, simulaciones y contenido generado con automatización o inteligencia artificial son orientativos y pueden contener errores.</p>
      <h2>3. No constituye asesoría profesional</h2><p>El servicio no es un banco, entidad financiera, contador, asesor de inversiones, abogado ni asesor tributario. No ejecuta inversiones ni garantiza ahorro, rentabilidad, eliminación de deudas o resultados económicos. Las decisiones finales pertenecen al usuario, quien debe verificar la información y buscar asesoría profesional cuando corresponda.</p>
      <h2>4. Cuenta y seguridad</h2><p>El usuario debe suministrar información correcta, proteger el acceso a su cuenta, mantener seguro su dispositivo y avisar sobre accesos no autorizados. No puede compartir cuentas, suplantar personas, intentar vulnerar el sistema ni usarlo con fines ilícitos.</p>
      <h2>5. Datos ingresados y autorizaciones</h2><p>El usuario conserva la titularidad de sus datos y autoriza su tratamiento únicamente para prestar, mantener, proteger y mejorar las funciones solicitadas. Es responsable de contar con autorización cuando incorpore información de terceras personas.</p>
      <h2>6. Planes, promoción y pagos</h2><p>El plan Gratis no tiene costo. Basic y VIP estarán disponibles gratuitamente hasta el 31 de diciembre de 2026. A partir del 1 de enero de 2027 sus precios mensuales de lanzamiento son ₡2.990 y ₡4.990, respectivamente. La promoción no genera cobros automáticos ni obliga a contratar. Para continuar con un plan pagado, el usuario deberá iniciar y confirmar un pago por el método disponible en ese momento.</p>
      <h2>7. Activación y comprobantes</h2><p>Cuando existan pagos por SINPE Móvil, el plan se activa únicamente después de validar monto, código y confirmación bancaria. Subir un comprobante no constituye por sí solo confirmación del pago. Los pagos duplicados o incorrectos serán revisados individualmente.</p>
      <h2>8. Disponibilidad y cambios</h2><p>El servicio puede cambiar, suspender funciones o presentar interrupciones por mantenimiento, seguridad, proveedores o causas fuera de control razonable. Los cambios materiales en precios o condiciones se informarán antes de aplicarse y podrán requerir una nueva aceptación.</p>
      <h2>9. Propiedad intelectual</h2><p>El software, diseño, marca, contenido y modelos propios pertenecen a sus respectivos titulares. La cuenta otorga una licencia personal, limitada, revocable y no transferible para usar el servicio; no permite copiar, revender, descompilar o explotar indebidamente sus componentes.</p>
      <h2>10. Suspensión y cierre</h2><p>Una cuenta puede suspenderse por fraude, abuso, incumplimiento, riesgo de seguridad o exigencia legal. El usuario puede dejar de usar el servicio y solicitar la eliminación de su cuenta y datos, sujeto a información que deba conservarse para cumplir obligaciones legales, resolver pagos o defender reclamaciones.</p>
      <h2>11. Responsabilidad</h2><p>El servicio se presta con cuidado razonable, pero no se garantiza que sea ininterrumpido o completamente libre de errores. En la medida permitida por la legislación aplicable, no se responde por decisiones financieras tomadas exclusivamente a partir de estimaciones o datos incorrectos ingresados por el usuario. Esta cláusula no limita derechos irrenunciables del consumidor.</p>
      <h2>12. Legislación y contacto</h2><p>Estos términos se interpretan conforme a las leyes de Costa Rica. Las dudas, solicitudes o reclamos pueden enviarse mediante la sección de Reportes o a <a href="mailto:soporte@dincr.com">soporte@dincr.com</a>. Se procurará resolver cualquier diferencia de buena fe antes de acudir a las autoridades competentes.</p>
    </section>
  </>;
}

function PrivacyPage() {
  return <>
    <span className="public-kicker">VERSIÓN 2026-09-23-v2 · VIGENTE DESDE EL 23 DE SEPTIEMBRE DE 2026</span>
    <h1>Política de Privacidad</h1>
    <p className="public-lead">Esta política explica cómo DINCR trata datos personales conforme a los principios de consentimiento informado, finalidad, proporcionalidad, calidad, seguridad y confidencialidad.</p>
    <section className="public-copy legal-copy">
      <h2>1. Responsable</h2><p>El responsable del tratamiento es Kenneth Andrés Alvarado Obando, Costa Rica, desarrollador y operador de DINCR. Las solicitudes se reciben mediante Reportes o en <a href="mailto:soporte@dincr.com">soporte@dincr.com</a>.</p>
      <h2>2. Datos tratados</h2><p>Podemos tratar identificación y cuenta —nombre, correo e identificadores técnicos—; información financiera ingresada por el usuario —ingresos, gastos, saldos, deudas, metas y presupuestos—; comprobantes de pago; eventos de uso, diagnósticos de errores y datos básicos del dispositivo; y contenido de integraciones que el usuario conecte expresamente.</p>
      <h2>3. Finalidades</h2><p>Los datos se usan para autenticar la cuenta, prestar funciones financieras, calcular resúmenes y simulaciones, sincronizar información autorizada, validar suscripciones, atender soporte, prevenir fraude, proteger el servicio, diagnosticar fallos y mejorar estabilidad y experiencia. No se venden ni se usan para publicidad de terceros.</p>
      <h2>4. Base del tratamiento</h2><p>El tratamiento necesario para prestar el servicio se realiza con el consentimiento informado del usuario y para ejecutar las funciones que solicita. Ciertas evidencias pueden conservarse para seguridad, cumplimiento de obligaciones y atención de reclamaciones. El consentimiento de comunicaciones promocionales, si se ofrece, será separado y opcional.</p>
      <h2>5. Proveedores y transferencias</h2><p>Para operar el servicio pueden intervenir proveedores de autenticación, base de datos, alojamiento, distribución móvil, monitoreo, correo e inteligencia artificial, incluidos Supabase, Render, Firebase/Google y servicios equivalentes. Solo reciben la información necesaria para su función y pueden procesarla fuera de Costa Rica bajo sus medidas y condiciones de protección.</p>
      <h2>6. Integraciones de Google</h2><p>Cuando el usuario conecta Google, el acceso autorizado se limita a las funciones solicitadas. Los datos de Google no se venden ni se utilizan para anuncios. Su uso se ajusta a la <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">Política de Datos de Usuario de los Servicios API de Google</a>, incluidos los requisitos de Uso Limitado.</p>
      <h2>7. Conservación</h2><p>Los datos se conservan mientras la cuenta esté activa o sean necesarios para prestar el servicio. Tras una solicitud de eliminación se borrarán o anonimizarán dentro de un plazo razonable, salvo registros que deban conservarse temporalmente por seguridad, pagos, copias de respaldo, obligaciones legales o reclamaciones.</p>
      <h2>8. Seguridad</h2><p>Aplicamos autenticación, separación de información por cuenta, controles de acceso, conexiones seguras, registros de auditoría y acceso limitado a proveedores necesarios. Ningún sistema es infalible; ante un incidente relevante se tomarán medidas de contención y se comunicará cuando corresponda.</p>
      <h2>9. Derechos del usuario</h2><p>El usuario puede solicitar acceso a sus datos, rectificación, actualización, eliminación o revocación del consentimiento cuando proceda. También puede desconectar integraciones desde el proveedor correspondiente. La revocación no afecta tratamientos ya realizados legítimamente y puede impedir que ciertas funciones continúen.</p>
      <h2>10. Decisiones automatizadas</h2><p>Las recomendaciones y clasificaciones financieras pueden generarse automáticamente a partir de los datos disponibles, pero son informativas y no producen por sí mismas una decisión bancaria, crediticia, laboral o jurídica vinculante.</p>
      <h2>11. Menores y terceros</h2><p>El servicio no está dirigido a menores de 18 años. No deben ingresarse datos de terceros sin una base legítima o autorización correspondiente.</p>
      <h2>12. Cambios</h2><p>Si esta política cambia materialmente, se mostrará la nueva versión y podrá solicitarse una aceptación renovada antes de continuar usando la aplicación.</p>
    </section>
  </>;
}

export default function PublicInfoPage() {
  return <main className="public-info-shell">
    <nav className="public-info-nav" aria-label="Información pública"><a className="public-brand" href="/about">DINCR</a><div><a className={!isPrivacy&&!isTerms&&!isDeletion?"active":""} href="/about">Acerca de</a><a className={isTerms?"active":""} href="/terms">Términos</a><a className={isPrivacy?"active":""} href="/privacy">Privacidad</a><a className={isDeletion?"active":""} href="/delete-account">Eliminar cuenta</a></div></nav>
    <div className="public-info-content">{isDeletion ? <DeleteAccountPage/> : isTerms ? <TermsPage/> : isPrivacy ? <PrivacyPage/> : <AboutPage/>}</div>
    <footer><span>DINCR · Costa Rica</span><div><a href="/terms">Términos</a> · <a href="/privacy">Privacidad</a> · <a href="/delete-account">Eliminar cuenta</a></div></footer>
  </main>;
}
