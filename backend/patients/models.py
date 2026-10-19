from django.db import models

class Patient(models.Model):
    age = models.PositiveIntegerField(null=True, blank=True)

class Study(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="studies")
    study_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Image(models.Model):
    class Modality(models.TextChoices):
        MAMMOGRAFIA = "mammografia"
        USG = "usg"

    study = models.ForeignKey(Study, on_delete=models.CASCADE, related_name="images")
    modality = models.CharField(max_length=20, choices=Modality.choices)
    image_path = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)