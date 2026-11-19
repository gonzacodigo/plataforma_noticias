from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("noticia", "0005_scraperun_alter_categoria_options_and_more")]
    operations = [migrations.CreateModel(
        name="NoticiaAlias",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("original_id", models.PositiveBigIntegerField(unique=True)),
            ("noticia", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aliases", to="noticia.noticia")),
        ],
    )]
