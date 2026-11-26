# Especificación de la funcionalidad: Álbumes de fotos compartidos

**Rama de la funcionalidad**: `001-albumes-compartidos`
**Creada**: 2026-11-20
**Estado**: Borrador
**Entrada**: Descripción del usuario: "Que las familias creen álbumes de fotos compartidos, inviten a sus parientes con un enlace y reciban un resumen semanal de las fotos nuevas."

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia de usuario 1 - Crear un álbum y subir fotos (Prioridad: P1)

Un usuario crea un álbum, le pone nombre y sube fotos desde el móvil o el ordenador.

**Por qué esta prioridad**: Sin álbumes ni subidas no hay producto.

**Prueba independiente**: Crear un álbum, subir 10 fotos y verlas en una cuadrícula ordenadas por fecha de captura.

**Escenarios de aceptación**:

1. **Dado** un usuario con sesión iniciada, **cuando** crea un álbum llamado "Verano 2026", **entonces** aparece en su lista de álbumes.
2. **Dado** un álbum, **cuando** el usuario sube 10 fotos JPEG, **entonces** aparecen las 10 ordenadas por fecha EXIF.

---

### Historia de usuario 2 - Invitar a los parientes con un enlace (Prioridad: P1)

El dueño del álbum comparte un enlace de invitación. Cualquiera que tenga el enlace puede ver y añadir fotos.

**Por qué esta prioridad**: Compartir es la propuesta de valor principal.

**Prueba independiente**: Abrir el enlace de invitación en una ventana privada, unirse y subir una foto.

---

### Historia de usuario 3 - Correo con el resumen semanal (Prioridad: P2)

Los miembros reciben cada semana un correo con miniaturas de las fotos nuevas de sus álbumes.

**Por qué esta prioridad**: Hace que la gente vuelva, pero el producto funciona sin él.

---

### Casos límite

- ¿Qué pasa si un enlace de invitación se filtra públicamente? [NEEDS CLARIFICATION: ¿los enlaces deben caducar o poder revocarse?]
- ¿Cómo se gestionan las subidas duplicadas de la misma foto?
- ¿Qué pasa con las fotos de un miembro cuando abandona el álbum? [NEEDS CLARIFICATION: ¿sus fotos se quedan o se eliminan?]

## Requisitos *(obligatorio)*

### Requisitos funcionales

- **FR-001**: El sistema DEBE permitir a los usuarios con sesión iniciada crear álbumes con un nombre de hasta 80 caracteres.
- **FR-002**: El sistema DEBE aceptar subidas JPEG, PNG y HEIC de hasta 25 MB cada una.
- **FR-003**: El sistema DEBE generar un enlace de invitación único por álbum.
- **FR-004**: Cualquiera con un enlace de invitación DEBE poder ver y subir fotos a ese álbum.
- **FR-005**: El sistema DEBE enviar un correo con el resumen semanal cada lunes a las 08:00 en la zona horaria del miembro.
- **FR-006**: El sistema DEBE eliminar la ubicación GPS de los metadatos EXIF antes de que otros miembros vean las fotos.
- **FR-007**: El sistema DEBE conservar los archivos originales durante [NEEDS CLARIFICATION: no se ha definido el plazo de conservación].

### Entidades clave

- **Álbum**: nombre, dueño, token de invitación, fecha de creación.
- **Foto**: archivo, álbum, quien la sube, fecha de captura, fecha de subida.
- **Membresía**: usuario, álbum, rol (dueño, miembro), fecha de alta.

## Criterios de éxito *(obligatorio)*

- **SC-001**: El 80 % de los álbumes nuevos recibe al menos un miembro invitado en 7 días.
- **SC-002**: Subir 10 fotos tarda menos de 30 segundos con una conexión de 20 Mbps.
