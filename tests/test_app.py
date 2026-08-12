from fastapi.testclient import TestClient


def create_client(client: TestClient, name: str = "Анна Волкова") -> str:
    response = client.post(
        "/clients/new",
        data={
            "name": name,
            "company": "North Studio",
            "email": "anna@example.com",
            "phone": "+7 999 123-45-67",
            "client_status": "active",
            "note": "Обсудить следующий этап в пятницу",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"]


def test_dashboard_is_available(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Добрый день" in response.text
    assert "Всего клиентов" in response.text


def test_client_and_deal_flow(client: TestClient) -> None:
    client_location = create_client(client)

    detail = client.get(client_location)
    assert detail.status_code == 200
    assert "Анна Волкова" in detail.text
    assert "North Studio" in detail.text

    deal = client.post(
        "/deals/new",
        data={
            "title": "Корпоративный сайт",
            "amount": "85000",
            "client_id": "1",
            "stage": "proposal",
        },
        follow_redirects=False,
    )
    assert deal.status_code == 303

    deals = client.get("/deals")
    assert "Корпоративный сайт" in deals.text
    assert "85 000 ₽" in deals.text

    stage = client.post(
        "/deals/1/stage",
        data={"stage": "won"},
        follow_redirects=False,
    )
    assert stage.status_code == 303

    dashboard = client.get("/")
    assert "85 000 ₽" in dashboard.text


def test_client_search(client: TestClient) -> None:
    create_client(client, name="Мария Орлова")

    found = client.get("/clients", params={"q": "Орлова"})
    missing = client.get("/clients", params={"q": "Петров"})

    assert "Мария Орлова" in found.text
    assert "Ничего не найдено" in missing.text


def test_invalid_deal_stage_is_rejected(client: TestClient) -> None:
    create_client(client)
    client.post(
        "/deals/new",
        data={"title": "Айдентика", "amount": "30000", "client_id": "1"},
    )

    response = client.post("/deals/1/stage", data={"stage": "unknown"})

    assert response.status_code == 400
