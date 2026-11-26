# Álbumes familiares: un enlace que lo abre todo

**Lucía:** Hola, Álex. Hoy toca revisar una especificación que parece sencilla: álbumes de fotos compartidos para familias.

**Álex:** Parece sencilla, sí. Pero he visto una frase que me ha quitado el sueño: cualquiera que tenga el enlace puede ver y subir fotos. `spec.md:56`

**Lucía:** Llegaremos ahí, te lo prometo. Primero, situemos a quien nos escucha.

**Lucía:** La idea es que una familia cree un álbum, invite a sus parientes con un enlace y reciba cada semana un correo con las fotos nuevas. `spec.md:6`

**Álex:** O sea, tres piezas: crear y subir, invitar, y el resumen semanal.

**Lucía:** Exacto. Las dos primeras son la prioridad máxima. El correo semanal es secundario: ayuda a que la gente vuelva, pero el producto funciona sin él. `spec.md:39`

**Álex:** Eso me parece sensato. Si hay que recortar, se recorta por el correo. Vale, ¿y cómo se suben las fotos?

**Lucía:** Aquí hay una decisión técnica bonita. El navegador sube las fotos directamente al almacenamiento, con enlaces firmados, sin pasar por el servidor de la aplicación. `research.md:5`

**Lucía:** Así los archivos de hasta veinticinco megas no saturan la aplicación, y se cumple el objetivo de subir diez fotos en menos de treinta segundos. `research.md:6` `spec.md:70`

**Álex:** Me gusta, pero tengo una pega. Descartaron las subidas reanudables. `research.md:7`

**Álex:** Piensa en la abuela subiendo fotos desde el móvil, con mala cobertura. Si se corta a mitad de una foto de veinte megas, ¿empieza otra vez desde cero?

**Lucía:** Sí, empezaría de cero. Es un riesgo real. Para la primera versión puede valer, pero conviene medirlo pronto.

**Álex:** Y ahí va mi segunda pega: la prueba de los treinta segundos está en la última fase del plan. Si falla, lo descubrimos al final. `tasks.md:37`

**Lucía:** Buen punto. Yo haría una prueba rápida con conexión lenta justo después de tener el endpoint de subida, no al final.

**Álex:** De acuerdo. Ahora sí: hablemos del enlace mágico.

**Lucía:** Vale. La decisión es un único enlace permanente por álbum. Quien lo tenga entra como miembro, con permiso para ver y para subir. `research.md:11`

**Lucía:** La razón es la fricción. Los familiares no son técnicos, y pedirles crear cuentas o aceptar invitaciones por correo los espanta. `research.md:12`

**Álex:** Lo entiendo. Pero un enlace permanente es una llave maestra. Si alguien lo reenvía a un grupo de mensajería, o acaba publicado, ¿qué pasa?

**Lucía:** Pues la propia especificación lo pregunta y no lo responde. Está marcado como pendiente: ¿los enlaces caducan o se pueden revocar? `spec.md:45`

**Álex:** Y no es solo que un extraño vea las fotos de tu familia. Es que puede subir lo que quiera al álbum.

**Álex:** No veo en ningún sitio que el dueño pueda borrar fotos que subieron otros. Ni moderación, ni nada.

**Lucía:** Tienes razón, no aparece. Las alternativas que se descartaron eran invitaciones personales, enlaces que caducan, o enlaces de solo lectura con aprobación para subir. `research.md:13`

**Álex:** Yo no digo que haya que elegir la más estricta. Pero sí poder revocar el enlace y que el dueño pueda borrar fotos. Eso lo metería en la primera versión.

**Lucía:** Me parece un término medio razonable: misma facilidad para entrar, pero con un botón de emergencia.

**Álex:** Siguiente tema: privacidad de las fotos. ¿Qué pasa con la ubicación que guardan los móviles?

**Lucía:** Eso está bien pensado. Antes de que otros miembros vean una foto, se elimina la ubicación de sus metadatos. `spec.md:58`

**Álex:** Antes de que otros la vean. Pero el original se guarda tal cual, con la ubicación dentro. `research.md:17`

**Álex:** Y cuánto tiempo se guardan los originales tampoco está decidido. `spec.md:59`

**Lucía:** Cierto. Y va de la mano de otra pregunta abierta en el plan: cuál es el presupuesto de almacenamiento por familia. `plan.md:19`

**Álex:** Originales de hasta veinticinco megas, más las copias convertidas, sin límite de tiempo ni de espacio. Eso, con cinco mil familias, es una factura que crece sola.

**Lucía:** Vamos con el correo semanal, que tiene un detalle curioso. Sale los lunes a las ocho de la mañana en la zona horaria de cada miembro. `spec.md:57`

**Lucía:** Para no programar un envío por persona, hay una tarea que se ejecuta cada hora y escoge a quién le toca. `research.md:23`

**Álex:** Elegante. Pero hay zonas horarias con media hora, como la India. Si la tarea corre en horas en punto, esas personas nunca coinciden con las ocho exactas.

**Lucía:** Es un caso borde, pero fácil de arreglar si se trata como una ventana y no como una hora exacta.

**Álex:** Y otra cosa: el requisito dice que el sistema debe enviar el correo. ¿Nadie puede darse de baja? Eso suele ser obligatorio por ley.

**Lucía:** No se menciona. Lo apuntamos como pregunta.

**Álex:** También hay casos borde que se listan pero no tienen respuesta. Por ejemplo, qué pasa si alguien sube dos veces la misma foto. `spec.md:46`

**Lucía:** Y qué pasa con las fotos de alguien que abandona el álbum. ¿Se quedan o se van con él? Eso también está pendiente. `spec.md:47`

**Álex:** Resumiendo, la especificación es clara en lo técnico, pero deja abiertas justo las decisiones que afectan a la confianza de las familias.

**Lucía:** Así que, a quien esté revisando, esto es lo que te toca decidir.

**Lucía:** Primero: si el enlace de invitación se puede revocar o caduca, sabiendo que da permiso para subir.

**Lucía:** Segundo: qué pasa con las fotos de quien se va del álbum, y si el dueño puede borrar fotos de otros.

**Lucía:** Y tercero: cuánto tiempo se guardan los originales, con su ubicación, y cuánto espacio tiene cada familia.

**Álex:** Y un consejo extra: adelantad la prueba de velocidad de subida. Mejor descubrir el problema en la segunda semana que en la última.

**Lucía:** Perfecto. Gracias, Álex. Y a ti, gracias por escuchar en lugar de leer cinco documentos.

**Álex:** Hasta la próxima especificación.
