import { LockKeyhole, MailCheck, ShieldCheck } from "lucide-react";

const isPrivacy = window.location.pathname === "/privacy";

function AboutPage() {
  return (
    <>
      <span className="public-kicker">ASISTENTE FINANCIERO PERSONAL</span>
      <h1>J.A.R.V.I.S.</h1>
      <p className="public-lead">
        J.A.R.V.I.S. ayuda a su propietario a organizar gastos, deudas, metas y
        flujo de efectivo desde una experiencia privada y orientada a móvil.
      </p>

      <section className="public-feature-grid" aria-label="Funciones principales">
        <article>
          <MailCheck size={24} />
          <h2>Lectura financiera</h2>
          <p>Identifica notificaciones bancarias autorizadas por el usuario para preparar movimientos financieros.</p>
        </article>
        <article>
          <ShieldCheck size={24} />
          <h2>Control del usuario</h2>
          <p>Los movimientos detectados quedan pendientes de revisión y no se guardan automáticamente como gastos confirmados.</p>
        </article>
        <article>
          <LockKeyhole size={24} />
          <h2>Acceso limitado</h2>
          <p>Solicita acceso de solo lectura a Gmail. No envía, modifica ni elimina correos.</p>
        </article>
      </section>

      <section className="public-copy">
        <h2>Uso de datos de Google</h2>
        <p>
          El acceso a Gmail se usa exclusivamente para localizar correos financieros
          y extraer la información necesaria para las funciones solicitadas por el usuario.
          J.A.R.V.I.S. no utiliza esos datos para publicidad ni los vende a terceros.
        </p>
      </section>
    </>
  );
}

function PrivacyPage() {
  return (
    <>
      <span className="public-kicker">ÚLTIMA ACTUALIZACIÓN: 1 DE SEPTIEMBRE DE 2026</span>
      <h1>Política de privacidad</h1>
      <p className="public-lead">
        Esta política explica cómo J.A.R.V.I.S. accede, utiliza y protege los datos
        autorizados por su usuario.
      </p>

      <section className="public-copy">
        <h2>Datos a los que accede</h2>
        <p>
          Con autorización expresa, J.A.R.V.I.S. utiliza el alcance de Gmail de solo
          lectura para consultar mensajes y archivos adjuntos relacionados con
          notificaciones y estados de cuenta financieros.
        </p>

        <h2>Cómo se utilizan</h2>
        <p>
          Los datos se procesan para detectar movimientos, evitar duplicados, preparar
          candidatos de transacciones y facilitar la conciliación financiera. El sistema
          no envía, modifica ni elimina mensajes de Gmail.
        </p>

        <h2>Almacenamiento y protección</h2>
        <p>
          J.A.R.V.I.S. conserva únicamente la información necesaria para prestar sus
          funciones financieras y aplicar controles de deduplicación y auditoría. El
          acceso está restringido al propietario autenticado y a los servicios técnicos
          necesarios para operar la aplicación.
        </p>

        <h2>Divulgación y publicidad</h2>
        <p>
          Los datos de Google no se venden, no se usan para publicidad y no se comparten
          con terceros, salvo proveedores de infraestructura indispensables para operar
          la aplicación o cuando la ley lo exija.
        </p>

        <h2>Uso limitado de datos de Google</h2>
        <p>
          El uso y la transferencia de información recibida desde las APIs de Google se
          ajustan a la <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">Política de Datos de Usuario de los Servicios API de Google</a>,
          incluidos sus requisitos de Uso Limitado.
        </p>

        <h2>Control y eliminación</h2>
        <p>
          El usuario puede revocar el acceso desde la configuración de seguridad de su
          Cuenta de Google y solicitar la eliminación de los datos almacenados mediante
          el correo de asistencia mostrado en la pantalla de consentimiento de Google.
        </p>

        <h2>Cambios y contacto</h2>
        <p>
          Los cambios materiales se publicarán en esta página. Las consultas de privacidad
          pueden enviarse al correo de asistencia identificado en la pantalla OAuth de J.A.R.V.I.S.
        </p>
      </section>
    </>
  );
}

export default function PublicInfoPage() {
  return (
    <main className="public-info-shell">
      <nav className="public-info-nav" aria-label="Información pública">
        <a className="public-brand" href="/about">J.A.R.V.I.S.</a>
        <div>
          <a className={!isPrivacy ? "active" : ""} href="/about">Acerca de</a>
          <a className={isPrivacy ? "active" : ""} href="/privacy">Privacidad</a>
        </div>
      </nav>

      <div className="public-info-content">
        {isPrivacy ? <PrivacyPage /> : <AboutPage />}
      </div>

      <footer>
        <span>J.A.R.V.I.S. · Asistente financiero personal</span>
        <a href="/privacy">Política de privacidad</a>
      </footer>
    </main>
  );
}
