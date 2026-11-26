# Investigación: Álbumes de fotos compartidos

## Ruta de subida

- **Decisión**: El navegador sube directamente al almacenamiento de objetos con URL prefirmadas.
- **Justificación**: Evita que los archivos de 25 MB pasen por los servidores de la API y cumple el objetivo de subida de 30 s.
- **Alternativas consideradas**: Subir a través de la API; subidas reanudables con tus

## Modelo de invitación

- **Decisión**: Un único token de invitación permanente por álbum; quien tenga el enlace es miembro.
- **Justificación**: La menor fricción posible para familiares poco técnicos.
- **Alternativas consideradas**: Invitaciones personales por correo; enlaces que caducan; enlaces de solo lectura con aprobación para subir

## Soporte de HEIC

- **Decisión**: Convertir HEIC a JPEG en el proceso en segundo plano y conservar el original.
- **Justificación**: La mayoría de los navegadores no muestra HEIC.
- **Alternativas consideradas**: Rechazar HEIC; convertir en el navegador

## Envío del resumen

- **Decisión**: Una tarea de Celery beat cada hora que envía el resumen a los miembros cuya hora local sea el lunes a las 08:00.
- **Justificación**: Respeta las zonas horarias sin una tarea por usuario.
- **Alternativas consideradas**: Una tarea programada por usuario; enviar a todos a las 08:00 UTC
