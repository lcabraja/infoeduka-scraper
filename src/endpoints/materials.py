import click
import requests, asyncio, os
from credentials import FILE_MATERIALS, get_filename, try_read_file, write_file

from session import get_materials

# TODO put everything in the cache and copy from there
outdir = os.getcwd()

def parse_materials(materials_response):
    materials_data = {}
    for semester in materials_response["data"]:
        for year in semester["godine"]:
            for subject in year["predmeti"]:
                materials_data[subject["idPredmet"]] = {
                    # semester
                    "academic_year": semester["akademskaGodina"],
                    "semester": semester["semestar"],

                    # year
                    "track": year["studij"],
                    "subtrack": year["smjer"],
                    "year": year["godina"],
                    "enrollment": year["nacin"],
                    "group": year["grupa"],

                    # subject
                    "name": subject["predmet"],
                    "code": subject["sifra"],
                    "ects": subject["ects"],
                    "signature": subject["potpis"],
                    "signature_date": subject["potpisDatum"],
                    "grade": subject["ocjena"],
                    "grade_desc": subject["ocjenaOpisno"],
                    "grade_date": subject["ocjenaDatum"],
                    "passed_nograde": subject["polozenBezOcjene"],
                    "passed_nograde_kolok": subject["polozenBezOcjeneKolokviran"],
                    "accepted": subject["priznat"],
                    "accepted_cert": subject["priznatCertifikat"],

                    "materials": {
                        "count": subject["dodatno"]["materijali"]["brojMaterijala"],
                        "last_changed_dotw": subject["dodatno"]["materijali"]["zadnjaIzmjenaDanUTjednu"],
                        "last_changed_date": subject["dodatno"]["materijali"]["zadnjaIzmjenaDatum"],
                        "last_changed_user": subject["dodatno"]["materijali"]["zadnjaIzmjenaKorisnik"],
                        "files": {}
                    }
                }

                for category in subject["dodatno"]["materijali"]["kategorije"]:
                    materials_data[subject["idPredmet"]]["materials"]["files"][category["kategorija"]] = {}
                    for material in category["materijali"]:
                        materials_data[subject["idPredmet"]]["materials"]["files"][category["kategorija"]][material["id"]] = {
                            "filename": material["naziv"],
                            "description": material["opis"],
                            "bytes": material["velicina"],
                            "date_uploaded": material["vrijeme"],
                            "user_uploaded": material["korisnika"],
                            "content_type": material["contentType"],
                            "url": material["link"],
                            "downloaded": False,

                            "subject_name": subject["predmet"],
                            "subject_code": subject["sifra"],
                            "subject_id": subject["idPredmet"],
                            "mat_category": material["kategorija"]
                        }
    return materials_data

def materials_diff(old_materials_data, new_materials_data):
    if len(old_materials_data.keys()) > 0:
        for id_course, course in new_materials_data.items():
            if id_course in old_materials_data.keys() and course["materials"]["last_changed_date"] == old_materials_data[id_course]["materials"]["last_changed_date"]:
                for category, files in course["materials"]["files"].items():
                    for id_file, file in files.items():
                        if category in old_materials_data[id_course]["materials"]["files"] and \
                            id_file in old_materials_data[id_course]["materials"]["files"][category] and \
                            old_materials_data[id_course]["materials"]["files"][category][id_file]["downloaded"] == True:
                            new_materials_data[id_course]["materials"]["files"][category][id_file]["downloaded"] = True

def category_path_from_file(file):
    basepath = os.path.join(os.getcwd(), os.path.join(outdir, file["subject_name"].replace("/", "-")))
    category_path = os.path.join(basepath, file["mat_category"].replace("/", "-"))
    return category_path

async def download(session_token, file_instance, index):
    try:
        baseurl = "https://student.racunarstvo.hr/digitalnareferada/"
        url = os.path.join(baseurl, file_instance["url"])
        
        path = category_path_from_file(file_instance)
        filepath = os.path.join(path, file_instance["filename"])
        copy_index = 1;
        while os.path.exists(filepath):
            filepath = os.path.join(path, file_instance["filename"] + f"_{copy_index}")
            copy_index += 1
        headers = {"Cookie": f"PHPSESSID={session_token}"}

        response = requests.get(url, headers=headers, stream=True)
        with open(filepath, "wb") as fout:
            for chunk in response.iter_content(chunk_size=4096):
                fout.write(chunk)
            print(f"Completed download of {file_instance['filename']}")
    except KeyboardInterrupt:
        click.echo(f"Aborting download, [{file_instance['filename']}] may be incomplete and won't work properly")
        click.Abort()
        return
        

async def download_materials(session_token, materials_data, semester_filter):
    queued_files = []
    for _, subject in materials_data.items():
        basepath = os.path.join(os.getcwd(), os.path.join(outdir, subject["name"].replace("/", "-")))
        if ('|'.join([subject["academic_year"], subject["semester"]]) == semester_filter):
            for category, files in subject["materials"]["files"].items():
                category_path = os.path.join(basepath, category.replace("/", "-"))
                if not os.path.exists(category_path): os.makedirs(category_path)
                for id, file in files.items():
                    if not file["downloaded"]:
                        queued_files.append((file))
    await asyncio.gather(*[download(session_token, file, index) for index, file in enumerate(queued_files)])

def materials_main(session_token):
    materials_path = get_filename(FILE_MATERIALS)
    last_data = try_read_file(materials_path) or {}
    materials_response_data = parse_materials(get_materials(session_token))
    materials_diff(last_data, materials_response_data)
    # TODO implement a filtering system
    # TODO implement a warning when downloading all files, only once
    semester_filter = "2022/2023|Zimski"
    try:
        asyncio.run(download_materials(session_token, materials_response_data, semester_filter))
    except KeyboardInterrupt:
        click.echo("Aborting download, some files may be incomplete and won't work properly")
        click.Abort()
    write_file(materials_path, materials_response_data)