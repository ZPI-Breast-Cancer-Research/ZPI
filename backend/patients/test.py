from django.test import TestCase
from patients.models import Patient, Study, Image
from mlops.models import ModelVersion, ReviewStatus
from extraction.models import ExtractionRun
from segmentation.models import SegmentationRun

class MedicalStructureTestCase(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(age=50)
        self.study = Study.objects.create(patient=self.patient)
        self.image = Image.objects.create(
            study=self.study,
            modality=Image.Modality.MAMMOGRAFIA,
            image_path="/data/images/test.dcm"
        )
        self.model_version = ModelVersion.objects.create(
            name="test_model",
            type=ModelVersion.ModelType.EXTRACTION,
            version="0.1"
        )

    def test_patient_study_image_relations(self):
        """Test proper foreign key cascade and related names."""
        self.assertEqual(self.patient.studies.first(), self.study)
        self.assertEqual(self.study.images.first(), self.image)
        self.assertEqual(self.image.study, self.study)

    def test_extraction_run_default_status(self):
        """Test extraction run creation and default pending status."""
        run = ExtractionRun.objects.create(
            study=self.study,
            model=self.model_version,
            result_predicted={"test": "data"}
        )
        self.assertEqual(run.status, ReviewStatus.PENDING)
        self.assertEqual(self.study.extraction_runs.first(), run)

    def test_segmentation_run_default_status(self):
        """Test segmentation run creation and default pending status."""
        run = SegmentationRun.objects.create(
            image=self.image,
            model=self.model_version,
            mask_path_predicted="/data/masks/pred.nii.gz"
        )
        self.assertEqual(run.status, ReviewStatus.PENDING)
        self.assertEqual(self.image.segmentation_runs.first(), run)