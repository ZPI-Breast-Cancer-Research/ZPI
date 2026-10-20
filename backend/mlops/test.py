from django.db import IntegrityError
from django.test import TestCase
from mlops.models import ModelVersion

class ModelVersionTestCase(TestCase):
    def setUp(self):
        ModelVersion.objects.create(
            name="unet_segmentation",
            type=ModelVersion.ModelType.SEGMENTATION,
            version="1.0.0"
        )

    def test_unique_constraint_name_version(self):
        """Ensure that creating a ModelVersion with the same name and version raises IntegrityError."""
        with self.assertRaises(IntegrityError):
            ModelVersion.objects.create(
                name="unet_segmentation",
                type=ModelVersion.ModelType.SEGMENTATION,
                version="1.0.0"
            )

    def test_different_version_allowed(self):
        """Ensure that the same name with a different version is allowed."""
        model_v2 = ModelVersion.objects.create(
            name="unet_segmentation",
            type=ModelVersion.ModelType.SEGMENTATION,
            version="2.0.0"
        )
        self.assertIsNotNone(model_v2.pk)