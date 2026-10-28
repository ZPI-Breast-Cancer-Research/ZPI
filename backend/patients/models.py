from django.db import models


class Study(models.Model):
    """
    Represents a patient study linked with the Orthanc PACS.
    """
    orthanc_path = models.CharField(max_length=255, help_text="Orthanc study ID or path")

    class Meta:
        db_table = 'studies'

    def __str__(self):
        return f"Study #{self.id} (Orthanc: {self.orthanc_path})"