<?php

namespace App\Http\Controllers\v1;

use App\Http\Controllers\Controller;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Request;
use Illuminate\Support\Facades\Validator;
use Illuminate\Support\Str;
use Yajra\Datatables\Datatables;
use App\Models\Assets\Asset;
use App\Models\Assets\AssetImage;
use App\Models\Assets\AssetNearbyPlace;
use App\Models\Assets\AssetPriceRent;
use App\Models\Assets\AssetSpecialFeature;
use App\Models\FileStorage;
use App\Models\Refs\RefDistrict;
use App\Models\Refs\RefLocation;
use App\Models\Refs\RefPriceRange;
use App\Models\Refs\RefProvince;
use App\Models\Refs\RefRoomRange;
use App\Models\Refs\RefTransisStation;
use App\Models\Refs\RefUsableAreaRange;
use App\Models\User;
use App\Models\Refs\RefTypeRent;
use App\Models\Refs\RefAirport;
use App\Models\Refs\RefHospital;
use App\Models\Refs\RefMall;
use App\Models\Refs\RefUniversity;
use App\Enums\Response;
use App\Enums\RefAnnouncementType;
use App\Enums\RefAssetStatus as RefAssetStatusEnum;
use Carbon\Carbon;

class AssetController extends Controller
{
    function __construct() { ini_set('max_execution_time', '600'); }

    private function fallbackAssetData($uuid = '')
    {
        return [
            "id" => 0,
            "uuid" => $uuid,
            "no" => "",
            "title_th" => "ประกาศนี้ไม่พร้อมใช้งาน",
            "title_en" => "Listing unavailable",
            "description_th" => "ขออภัย ไม่พบข้อมูลประกาศนี้ในระบบ กรุณากลับไปเลือกรายการอื่น",
            "description_en" => "This listing is unavailable. Please go back and browse other listings.",
            "contact_phone" => "",
            "contact_line" => "",
            "bathroom_quantity" => 0,
            "bedroom_quantity" => 0,
            "floor_quantity" => 0,
            "usable_area" => 0,
            "price_before_discount" => 0,
            "price" => 0,
            "latitude" => 0,
            "longitude" => 0,
            "created_by" => (object) ["id" => 0, "full_name_th" => "", "full_name_en" => ""],
            "updated_by" => (object) ["id" => 0, "full_name_th" => "", "full_name_en" => ""],
            "ref_announcer_status" => null,
            "ref_announcement_type" => null,
            "ref_asset_type" => null,
            "ref_location" => (object) [
                "id" => 0,
                "name_th" => "",
                "name_en" => "",
                "ref_district" => (object) ["id" => 0, "name_th" => "", "name_en" => ""],
                "ref_province" => (object) ["id" => 0, "name_th" => "", "name_en" => ""],
                "latitude" => "",
                "longitude" => "",
            ],
            "ref_asset_status" => null,
            "ref_province" => null,
            "asset_special_features" => [],
            "asset_nearby_places" => [],
            "cover_img" => (object) [
                "id" => 0,
                "name" => "no-image.png",
                "size" => 0,
                "type" => "image/png",
                "ext" => "png",
                "url" => $this->forceHttpsUrl('/images/no-image.png'),
            ],
            "asset_images" => [],
            "asset_price_rents" => [],
            "is_pet_friendly" => 0,
            "transis_stations" => [],
        ];
    }

    public function list(Datatables $datatables)
    {
        try {
            $request = mergePaginate($datatables->getRequest());

            $data = Asset::select(
                'asset.id',
                'asset.uuid',
                'asset.no',
                'asset.created_at',
                'asset.created_by',
                'asset.updated_at',
                'asset.updated_by',
                'asset.ref_announcer_status_id',
                'asset.ref_announcement_type_id',
                'asset.ref_asset_type_id',
                'asset.ref_location_id',
                'asset.name_th',
                'asset.title_th',
                'asset.bathroom_quantity',
                'asset.bedroom_quantity',
                'asset.floor_quantity',
                'asset.usable_area',
                'asset.price_before_discount',
                'asset.price',
                'asset.ref_asset_status_id',
                'asset.latitude',
                'asset.longitude',
                'asset.cover_img_id',
                'ref_location.name_th as ref_location_name_th',
                'ref_location.name_en as ref_location_name_en'
            )
                ->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id');

            if (!$request->sort_by || !$request->sort_type) {
                $data->orderBy('asset.updated_at', 'desc');
            } else {
                $data->orderBy($request->sort_by, $request->sort_type);
            }

            if ($request->search) {
                $arrayAssetIds = [];
                $search = strtolower($request->search);

                $refTransisStationIds = RefTransisStation::select('id')
                    ->whereRaw('LOWER(name_th) LIKE ?', [$search . '%'])
                    ->pluck('id')
                    ->toArray();
                $arrayAssetIds = array_merge(
                    $arrayAssetIds,
                    AssetNearbyPlace::getAssetNearbyPlaces()
                        ->select('asset_id')
                        ->where('ref_table_name', 'ref_transis_station')
                        ->whereIn('ref_id', $refTransisStationIds)
                        ->pluck('asset_id')
                        ->toArray()
                );

                $refUniversityIds = RefUniversity::select('id')
                    ->whereRaw('LOWER(name_th) LIKE ?', [$search . '%'])
                    ->pluck('id')
                    ->toArray();
                $arrayAssetIds = array_merge(
                    $arrayAssetIds,
                    AssetNearbyPlace::getAssetNearbyPlaces()
                        ->select('asset_id')
                        ->where('ref_table_name', 'ref_university')
                        ->whereIn('ref_id', $refUniversityIds)
                        ->pluck('asset_id')
                        ->toArray()
                );

                $refAirportIds = RefAirport::select('id')
                    ->whereRaw('LOWER(name_th) LIKE ?', [$search . '%'])
                    ->pluck('id')
                    ->toArray();
                $arrayAssetIds = array_merge(
                    $arrayAssetIds,
                    AssetNearbyPlace::getAssetNearbyPlaces()
                        ->select('asset_id')
                        ->where('ref_table_name', 'ref_airport')
                        ->whereIn('ref_id', $refAirportIds)
                        ->pluck('asset_id')
                        ->toArray()
                );

                $refMallIds = RefMall::select('id')
                    ->whereRaw('LOWER(name_th) LIKE ?', [$search . '%'])
                    ->pluck('id')
                    ->toArray();
                $arrayAssetIds = array_merge(
                    $arrayAssetIds,
                    AssetNearbyPlace::getAssetNearbyPlaces()
                        ->select('asset_id')
                        ->where('ref_table_name', 'ref_mall')
                        ->whereIn('ref_id', $refMallIds)
                        ->pluck('asset_id')
                        ->toArray()
                );

                $refHospitalIds = RefHospital::select('id')
                    ->whereRaw('LOWER(name_th) LIKE ?', [$search . '%'])
                    ->pluck('id')
                    ->toArray();
                $arrayAssetIds = array_merge(
                    $arrayAssetIds,
                    AssetNearbyPlace::getAssetNearbyPlaces()
                        ->select('asset_id')
                        ->where('ref_table_name', 'ref_hospital')
                        ->whereIn('ref_id', $refHospitalIds)
                        ->pluck('asset_id')
                        ->toArray()
                );

                $arrayAssetIds = array_unique($arrayAssetIds);
                $assetIdSql = count($arrayAssetIds) !== 0
                    ? ' OR asset.id IN (' . implode(',', $arrayAssetIds) . ')'
                    : '';

                $data->whereRaw(
                    '(LOWER(asset.name_th) LIKE ?
                    OR LOWER(ref_location.name_th) LIKE ?
                    OR LOWER(asset.title_th) LIKE ?
                    OR LOWER(asset.no) LIKE ?
                    )' . $assetIdSql,
                    [
                        '%' . $search . '%',
                        '%' . $search . '%',
                        '%' . $search . '%',
                        '%' . $search . '%',
                    ]
                );
            }

            if ($request->ref_asset_type_id) {
                $data->where('asset.ref_asset_type_id', $request->ref_asset_type_id);
            }

            if ($request->ref_announcement_type_id) {
                $data->where('asset.ref_announcement_type_id', $request->ref_announcement_type_id);
            }

            if ($request->ref_price_range_id) {
                $refPriceRange = RefPriceRange::getRefPriceRanges()->where('id', $request->ref_price_range_id)->first();
                $condition = getConditionStartEnd($refPriceRange);

                if ($condition['start'] != null) {
                    $data->where('asset.price', $condition['start']['operator'], $condition['start']['number']);
                }

                if ($condition['end'] != null) {
                    $data->where('asset.price', $condition['end']['operator'], $condition['end']['number']);
                }
            }

            if ($request->ref_room_range_id) {
                $refRoomRange = RefRoomRange::getRefRoomRanges()->where('id', $request->ref_room_range_id)->first();
                $condition = getConditionStartEnd($refRoomRange);

                if ($condition['start'] != null) {
                    $data->where('asset.bedroom_quantity', $condition['start']['operator'], $condition['start']['number']);
                }

                if ($condition['end'] != null) {
                    $data->where('asset.bedroom_quantity', $condition['end']['operator'], $condition['end']['number']);
                }
            }

            if ($request->ref_usable_area_range_id) {
                $refUsableAreaRange = RefUsableAreaRange::getRefUsableAreaRanges()->where('id', $request->ref_usable_area_range_id)->first();
                $condition = getConditionStartEnd($refUsableAreaRange);

                if ($condition['start'] != null) {
                    $data->where('asset.usable_area', $condition['start']['operator'], $condition['start']['number']);
                }

                if ($condition['end'] != null) {
                    $data->where('asset.usable_area', $condition['end']['operator'], $condition['end']['number']);
                }
            }

            if ($request->ref_special_feature_ids && $request->ref_special_feature_ids != "[]") {
                $dataAssetSpecialFeature = [];
                $arrayRefSpecialFeatureIds = json_decode($request->ref_special_feature_ids);

                foreach ($arrayRefSpecialFeatureIds as $arrayRefSpecialFeatureId) {
                    $assetSpecialFeatures = AssetSpecialFeature::getAssetSpecialFeatures()
                        ->where('ref_special_feature_id', $arrayRefSpecialFeatureId)
                        ->get();

                    foreach ($assetSpecialFeatures as $assetSpecialFeature) {
                        if (isset($dataAssetSpecialFeature[$assetSpecialFeature->asset_id])) {
                            $dataAssetSpecialFeature[$assetSpecialFeature->asset_id] += 1;
                        } else {
                            $dataAssetSpecialFeature[$assetSpecialFeature->asset_id] = 1;
                        }
                    }
                }

                $assetIds = [];
                foreach ($dataAssetSpecialFeature as $assetId => $count) {
                    if ($count == count($arrayRefSpecialFeatureIds)) {
                        $assetIds[] = $assetId;
                    }
                }
                $data->whereIn('asset.id', $assetIds);
            }

            if ($request->ref_asset_status_ids && $request->ref_asset_status_ids != "[]") {
                $arrayRefAssetStatusIds = json_decode($request->ref_asset_status_ids);
                $data->whereIn('asset.ref_asset_status_id', $arrayRefAssetStatusIds);
            }

            if ($request->created_by != '' && $request->created_by != 'null' && ($request->created_by || $request->created_by == 0)) {
                if ($request->created_by == 0) {
                    $data->where('asset.created_by', null)->where('asset.updated_by', null);
                } else {
                    $data->where(function ($query) use ($request) {
                        $query->where('asset.updated_by', $request->created_by)
                            ->orWhere(function ($query) use ($request) {
                                $query->whereNull('asset.updated_by')
                                    ->where('asset.created_by', $request->created_by);
                            });
                    });
                }
            }

            if ($request->ref_asset_type_other_id && $request->ref_asset_type_other_id != "[]") {
                $arrayRefAssetTypeOtherIds = json_decode($request->ref_asset_type_other_id);
                foreach ($arrayRefAssetTypeOtherIds as $arrayRefAssetTypeOtherId) {
                    switch ($arrayRefAssetTypeOtherId) {
                        case '1':
                            $data->where('asset.ref_announcer_status_id', 1);
                            break;
                        case '2':
                            $arrayAssetNearbyPlaceIds = AssetNearbyPlace::getAssetNearbyPlaces()
                                ->select('asset_id')
                                ->where('ref_table_name', 'ref_transis_station')
                                ->where('distance', '<=', '2000')
                                ->pluck('asset_id')
                                ->toArray();
                            $data->whereIn('asset.id', $arrayAssetNearbyPlaceIds);
                            break;
                        case '3':
                            $arrayAssetNearbyPlaceIds = AssetNearbyPlace::getAssetNearbyPlaces()
                                ->select('asset_id')
                                ->where('ref_table_name', 'ref_university')
                                ->where('distance', '<=', '1000')
                                ->pluck('asset_id')
                                ->toArray();
                            $data->whereIn('asset.id', $arrayAssetNearbyPlaceIds);
                            break;
                        case '4':
                            $data->where('asset.is_pet_friendly', 1);
                            break;
                        case '5':
                            $arrayAssetPriceRentIds = AssetPriceRent::getAssetPriceRents()
                                ->select('asset_id')
                                ->where('ref_type_rent_id', 1)
                                ->where('price', '>', 0)
                                ->pluck('asset_id')
                                ->toArray();
                            $data->whereIn('asset.id', $arrayAssetPriceRentIds);
                            break;
                        case '6':
                            $data->where('asset.ref_announcement_type_id', 3);
                            break;
                    }
                }
            }

            $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($_query) use ($request) {
                    mergePaginate($request);
                })
                ->editColumn('created_by', fn ($item) => (object) $this->resolveUserSummary($item->created_by))
                ->editColumn('updated_by', fn ($item) => (object) $this->resolveUserSummary($item->updated_by))
                ->addColumn('ref_announcer_status', function ($item) {
                    return $this->mapNamedReference($item->refAnnouncerStatus()->select('id', 'name_th', 'name_en')->first());
                })
                ->addColumn('ref_announcement_type', function ($item) {
                    return $this->mapNamedReference($item->refAnnouncementType()->select('id', 'name_th', 'name_en')->first());
                })
                ->addColumn('ref_asset_type', function ($item) {
                    return $this->mapNamedReference($item->refAssetType()->select('id', 'name_th', 'name_en')->first());
                })
                ->addColumn('ref_location', function ($item) {
                    return $this->mapRefLocationSummary(RefLocation::find($item->ref_location_id));
                })
                ->addColumn('ref_asset_status', function ($item) {
                    $refAssetStatus = $item->refAssetStatus()->select('id', 'name_th', 'name_en', 'color_code')->first();
                    return $this->mapNamedReference($refAssetStatus, [
                        'color_code' => $refAssetStatus?->color_code,
                    ]);
                })
                ->addColumn('cover_img', function ($item) {
                    $img = $this->mapFileStorage(FileStorage::find($item->cover_img_id));
                    return $img ? (object) $img : null;
                })
                ->removeColumn([
                    'ref_announcer_status_id',
                    'ref_announcement_type_id',
                    'ref_asset_type_id',
                    'ref_location_id',
                    'ref_asset_status_id',
                    'cover_img_id',
                    'ref_location_name_th',
                    'ref_location_name_en',
                ])
                ->make(true));
        } catch (\Exception $e) {
            \Log::error($e);
            return responseJson(Response::ERROR, $e->getMessage());
        }
    }

    public function dataMap()
    {
        try {
            $request = request();
            $limit = max(1, min((int) ($request->limit ?? 300), 300));

            $dataMapsQuery = Asset::select('asset.*')
                ->where('asset.is_active', true)
                ->whereNotNull('asset.latitude')
                ->whereNotNull('asset.longitude');

            if (is_numeric($request->maxLat) && is_numeric($request->minLat)) {
                $dataMapsQuery->whereBetween('asset.latitude', [(float) $request->minLat, (float) $request->maxLat]);
            }

            if (is_numeric($request->maxLon) && is_numeric($request->minLon)) {
                $dataMapsQuery->whereBetween('asset.longitude', [(float) $request->minLon, (float) $request->maxLon]);
            }

            $dataMaps = $dataMapsQuery
                ->orderBy('asset.updated_at', 'desc')
                ->limit($limit)
                ->get()
                ->map(function ($item) {
                    return [
                        "id" => $item->id,
                        "uuid" => $item->uuid,
                        "title_th" => $item->title_th,
                        "latitude" => (string) $item->latitude,
                        "longitude" => (string) $item->longitude,
                        "bathroom_quantity" => (int) $item->bathroom_quantity,
                        "bedroom_quantity" => (int) $item->bedroom_quantity,
                        "floor_quantity" => (int) $item->floor_quantity,
                        "usable_area" => (string) $item->usable_area,
                        "price_before_discount" => (string) $item->price_before_discount,
                        "price" => (string) $item->price,
                        "cover_img" => (object) $this->mapFileStorageWithFallback(FileStorage::find($item->cover_img_id)),
                    ];
                })
                ->values()
                ->all();

            $groupImages = [
                "ownerPost" => $this->buildGroupImageCards(
                    Asset::where('is_active', true)->where('ref_announcer_status_id', 1)->orderBy('updated_at', 'desc')->limit(6)->get()
                ),
                "nearByTransis" => $this->buildGroupImageCards(
                    Asset::where('is_active', true)
                        ->whereIn('id', AssetNearbyPlace::getAssetNearbyPlaces()
                            ->select('asset_id')
                            ->where('ref_table_name', 'ref_transis_station')
                            ->where('distance', '<=', '2000')
                            ->pluck('asset_id')
                            ->toArray())
                        ->orderBy('updated_at', 'desc')
                        ->limit(6)
                        ->get()
                ),
                "cityCenter" => $this->buildGroupImageCards(
                    Asset::where('is_active', true)
                        ->whereIn('id', AssetNearbyPlace::getAssetNearbyPlaces()
                            ->select('asset_id')
                            ->where('ref_table_name', 'ref_university')
                            ->where('distance', '<=', '1000')
                            ->pluck('asset_id')
                            ->toArray())
                        ->orderBy('updated_at', 'desc')
                        ->limit(6)
                        ->get()
                ),
            ];

            return responseJson(Response::SUCCESS, [
                "dataMaps" => $dataMaps,
                "groupImages" => $groupImages,
            ]);
        } catch (\Exception $exception) {
            \Log::error('AssetController@dataMap failed', [
                'message' => $exception->getMessage(),
                'trace' => $exception->getTraceAsString(),
            ]);

            return responseJson(Response::SUCCESS, [
                "dataMaps" => [],
                "groupImages" => [
                    "ownerPost" => [],
                    "nearByTransis" => [],
                    "cityCenter" => [],
                ],
            ]);
        }
    }

    public function listOwner(Datatables $datatables)
    {
        Request::merge(['ref_asset_type_other_id' => '[1]']);
        return $this->list($datatables);
    }

    public function listNearbyTransis(Datatables $datatables)
    {
        Request::merge(['ref_asset_type_other_id' => '[2]']);
        return $this->list($datatables);
    }

    public function listPetFriendly(Datatables $datatables)
    {
        Request::merge(['ref_asset_type_other_id' => '[4]']);
        return $this->list($datatables);
    }

    public function listShortTerm(Datatables $datatables)
    {
        Request::merge(['ref_asset_type_other_id' => '[5]']);
        return $this->list($datatables);
    }

    public function listNearbyUniversity(Datatables $datatables)
    {
        Request::merge(['ref_asset_type_other_id' => '[3]']);
        return $this->list($datatables);
    }

    public function data($uuid)
    {
        try {
            if (!preg_match('/^[0-9a-fA-F-]{8,36}$/', $uuid)) {
                return responseJson(Response::SUCCESS, $this->fallbackAssetData($uuid));
            }

            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) {
                return responseJson(Response::SUCCESS, $this->fallbackAssetData($uuid));
            }

            $createdBy = $this->resolveUserSummary($asset->created_by);
            $updatedBy = $this->resolveUserSummary($asset->updated_by);

            $refAnnouncerStatus = $asset->refAnnouncerStatus()->select('id', 'name_th', 'name_en')->first();
            $refAnnouncementType = $asset->refAnnouncementType()->select('id', 'name_th', 'name_en')->first();
            $refAssetType = $asset->refAssetType()->select('id', 'name_th', 'name_en')->first();
            $refAssetStatus = $asset->refAssetStatus()->select('id', 'name_th', 'name_en', 'color_code')->first();
            $refProvince = $asset->refProvince()->select('id', 'name_th', 'name_en', 'longitude', 'latitude')->first();

            if (!$refAnnouncerStatus || !$refAnnouncementType || !$refAssetType || !$refAssetStatus || !$refProvince) {
                \Log::warning('Asset detail has missing reference data', [
                    'uuid' => $uuid,
                    'ref_announcer_status' => (bool) $refAnnouncerStatus,
                    'ref_announcement_type' => (bool) $refAnnouncementType,
                    'ref_asset_type' => (bool) $refAssetType,
                    'ref_asset_status' => (bool) $refAssetStatus,
                    'ref_province' => (bool) $refProvince,
                ]);
            }

            $dataCoverImg = $this->mapFileStorage(FileStorage::find($asset->cover_img_id));

            $dataAssetImages = [];
            foreach ($asset->assetImages as $assetImage) {
                $img = $this->mapFileStorage(FileStorage::find($assetImage->file_storage_id));
                if ($img) {
                    $dataAssetImages[] = $img;
                }
            }

            $dataAssetNearbyPlaces = [];
            foreach ($asset->assetNearbyPlaces as $assetNearbyPlace) {
                $model = getTableNearbyPlace($assetNearbyPlace->ref_table_name);
                if (!$model) {
                    continue;
                }

                $place = $model->where('id', $assetNearbyPlace->ref_id)->first();
                if (!$place) {
                    continue;
                }

                $dataAssetNearbyPlaces[] = [
                    "id" => $assetNearbyPlace->id,
                    "name_th" => $place->name_th,
                    "name_en" => $place->name_en,
                    "distance" => round((float) $assetNearbyPlace->distance, 2),
                    "longitude" => $place->longitude,
                    "latitude" => $place->latitude,
                    "category" => $assetNearbyPlace->ref_table_name,
                ];
            }
            $dataAssetNearbyPlaces = collect($dataAssetNearbyPlaces)->sortBy('distance')->values()->all();

            $dataAssetSpecialFeatures = [];
            foreach ($asset->assetSpecialFeatures as $assetSpecialFeature) {
                $refSpecialFeature = $assetSpecialFeature->refSpecialFeature;
                if (!$refSpecialFeature) {
                    continue;
                }

                $dataAssetSpecialFeatures[] = [
                    "id" => $refSpecialFeature->id,
                    "name_th" => $refSpecialFeature->name_th,
                    "name_en" => $refSpecialFeature->name_en,
                    "img_url" => $this->forceHttpsUrl($refSpecialFeature->icon ?? '/images/no-image.png'),
                ];
            }

            $refLocation = RefLocation::find($asset->ref_location_id);
            $dataRefLocation = [];
            if ($refLocation) {
                $refDistrict = RefDistrict::find($refLocation->ref_district_id);
                $refLocationProvince = RefProvince::find($refLocation->ref_province_id);

                $dataRefLocation = [
                    "id" => $refLocation->id,
                    "name_th" => $refLocation->name_th,
                    "name_en" => $refLocation->name_en,
                    "ref_district" => (object) [
                        "id" => $refDistrict?->id,
                        "name_th" => $refDistrict?->name_th,
                        "name_en" => $refDistrict?->name_en,
                    ],
                    "ref_province" => (object) [
                        "id" => $refLocationProvince?->id,
                        "name_th" => $refLocationProvince?->name_th,
                        "name_en" => $refLocationProvince?->name_en,
                    ],
                    "latitude" => $refLocation->latitude,
                    "longitude" => $refLocation->longitude,
                ];
            }

            $dataAssetPriceRents = [];
            foreach ($asset->assetPriceRents as $assetPriceRent) {
                if (!$assetPriceRent->refTypeRent) {
                    continue;
                }

                $dataAssetPriceRents[] = [
                    "id" => $assetPriceRent->id,
                    "ref_price_rent" => [
                        "id" => $assetPriceRent->refTypeRent->id,
                        "name_th" => $assetPriceRent->refTypeRent->name_th,
                        "name_en" => $assetPriceRent->refTypeRent->name_en,
                    ],
                    "price" => $assetPriceRent->price,
                ];
            }

            $dataTrasisStations = collect($dataAssetNearbyPlaces)
                ->filter(fn ($item) => ($item['category'] ?? null) === 'ref_transis_station')
                ->values()
                ->all();

            $data = [
                "id" => $asset->id,
                "uuid" => $asset->uuid,
                "no" => $asset->no,
                "created_at" => $asset->created_at,
                "created_by" => (object) $createdBy,
                "updated_at" => $asset->updated_at,
                "updated_by" => (object) $updatedBy,
                "ref_announcer_status" => $refAnnouncerStatus ? [
                    "id" => $refAnnouncerStatus->id,
                    "name_th" => $refAnnouncerStatus->name_th,
                    "name_en" => $refAnnouncerStatus->name_en,
                ] : null,
                "ref_announcement_type" => $refAnnouncementType ? [
                    "id" => $refAnnouncementType->id,
                    "name_th" => $refAnnouncementType->name_th,
                    "name_en" => $refAnnouncementType->name_en,
                ] : null,
                "ref_asset_type" => $refAssetType ? [
                    "id" => $refAssetType->id,
                    "name_th" => $refAssetType->name_th,
                    "name_en" => $refAssetType->name_en,
                ] : null,
                "ref_location" => (object) $dataRefLocation,
                "contact_phone" => $asset->contact_phone,
                "contact_line" => $asset->contact_line,
                "name_th" => $asset->name_th,
                "name_en" => $asset->name_en,
                "title_th" => $asset->title_th,
                "title_en" => $asset->title_en,
                "description_th" => $asset->description_th,
                "description_en" => $asset->description_en,
                "bathroom_quantity" => $asset->bathroom_quantity,
                "bedroom_quantity" => $asset->bedroom_quantity,
                "floor_quantity" => $asset->floor_quantity,
                "usable_area" => doubleval($asset->usable_area),
                "price_before_discount" => doubleval($asset->price_before_discount),
                "price" => doubleval($asset->price),
                "ref_asset_status" => $refAssetStatus ? [
                    "id" => $refAssetStatus->id,
                    "name_th" => $refAssetStatus->name_th,
                    "name_en" => $refAssetStatus->name_en,
                    "color_code" => $refAssetStatus->color_code,
                ] : null,
                "longitude" => $asset->longitude,
                "latitude" => $asset->latitude,
                "ref_province" => $refProvince ? [
                    "id" => $refProvince->id,
                    "name_th" => $refProvince->name_th,
                    "name_en" => $refProvince->name_en,
                    "longitude" => $refProvince->longitude,
                    "latitude" => $refProvince->latitude,
                ] : null,
                "asset_special_features" => $dataAssetSpecialFeatures,
                "asset_nearby_places" => $dataAssetNearbyPlaces,
                "cover_img" => $dataCoverImg ? (object) $dataCoverImg : null,
                "asset_images" => $dataAssetImages,
                "asset_price_rents" => $dataAssetPriceRents,
                "is_pet_friendly" => (int) $asset->is_pet_friendly,
                "transis_stations" => $dataTrasisStations,
            ];

            return responseJson(Response::SUCCESS, $data);
        } catch (\Exception $exception) {
            \Log::error('AssetController@data failed', [
                'uuid' => $uuid,
                'message' => $exception->getMessage(),
                'trace' => $exception->getTraceAsString(),
            ]);
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    private function resolveUserSummary($userId): array
    {
        $userRaw = $userId ? User::getUserById($userId) : null;
        $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;

        if (!$user) {
            return [
                "id" => "0",
                "full_name_th" => "Anonymous",
                "full_name_en" => "Anonymous",
            ];
        }

        return [
            "id" => $user->id,
            "full_name_th" => $user->fullnameth ?? $user->full_name_th ?? '',
            "full_name_en" => $user->fullnameen ?? $user->full_name_en ?? '',
        ];
    }

    private function forceHttpsUrl($path): string
    {
        $generated = url($path);
        return preg_replace('/^http:\/\//i', 'https://', $generated);
    }

    private function mapFileStorage($file): ?array
    {
        if (!$file) {
            return null;
        }

        return [
            "id" => $file->id,
            "name" => $file->file_name,
            "size" => $file->file_size,
            "type" => $file->file_type,
            "ext" => str_replace('image/', '', $file->file_type),
            "url" => $this->forceHttpsUrl($file->file_path . '/' . $file->file_name),
        ];
    }

    private function mapFileStorageWithFallback($file): array
    {
        return $this->mapFileStorage($file) ?? [
            "id" => 0,
            "name" => "no-image.png",
            "size" => 0,
            "type" => "image/png",
            "ext" => "png",
            "url" => $this->forceHttpsUrl('/images/no-image.png'),
        ];
    }

    private function buildGroupImageCards($items): array
    {
        return collect($items)->map(function ($item) {
            return [
                "id" => $item->id,
                "uuid" => $item->uuid,
                "cover_img" => (object) $this->mapFileStorageWithFallback(FileStorage::find($item->cover_img_id)),
            ];
        })->values()->all();
    }

    private function mapNamedReference($model, array $extra = []): ?object
    {
        if (!$model) {
            return null;
        }

        return (object) array_merge([
            "id" => $model->id,
            "name_th" => $model->name_th,
            "name_en" => $model->name_en,
        ], $extra);
    }

    private function mapRefLocationSummary($refLocation): ?object
    {
        if (!$refLocation) {
            return null;
        }

        $refDistrict = RefDistrict::find($refLocation->ref_district_id);
        $refProvince = RefProvince::find($refLocation->ref_province_id);

        return (object) [
            "id" => $refLocation->id,
            "name_th" => $refLocation->name_th,
            "name_en" => $refLocation->name_en,
            "ref_district" => (object) [
                "id" => $refDistrict?->id,
                "name_th" => $refDistrict?->name_th,
                "name_en" => $refDistrict?->name_en,
            ],
            "ref_province" => (object) [
                "id" => $refProvince?->id,
                "name_th" => $refProvince?->name_th,
                "name_en" => $refProvince?->name_en,
            ],
            "latitude" => $refLocation->latitude,
            "longitude" => $refLocation->longitude,
        ];
    }

    private function updateStatusValidator($data)
    {
        $rules = [
            "ref_asset_status_id" => 'required',
        ];

        return validateMessage($data, $rules);
    }

    public function store()
    {
        try {
            DB::beginTransaction();

            $request = Request::all();
            $validatorMessages = $this->createAndUpdateValidator($request);
            if ($validatorMessages) {
                return responseJson(Response::VALIDATE, $validatorMessages);
            }

            $data = [
                'ref_announcer_status_id' => $request['ref_announcer_status_id'],
                'ref_announcement_type_id' => $request['ref_announcement_type_id'],
                'ref_asset_type_id' => $request['ref_asset_type_id'],
                'ref_location_id' => $request['ref_location_id'],
                'contact_phone' => isset($request['contact_phone']) ? $request['contact_phone'] : null,
                'contact_line' => isset($request['contact_line']) ? $request['contact_line'] : null,
                'latitude' => isset($request['latitude']) ? $request['latitude'] : null,
                'longitude' => isset($request['longitude']) ? $request['longitude'] : null,
                'created_by' => isset(Auth::user()->id) ? Auth::user()->id : null,
                'created_at' => Carbon::now(),
            ];

            $createAsset = Asset::create($data);
            if (!$createAsset) {
                return responseJson(Response::FAIL);
            }

            if ($request['ref_announcement_type_id'] == RefAnnouncementType::ForRent) {
                $refTypeRents = RefTypeRent::getRefTypeRents()->get();
                foreach ($refTypeRents as $refTypeRent) {
                    AssetPriceRent::create([
                        'asset_id' => $createAsset->id,
                        'ref_type_rent_id' => $refTypeRent->id,
                    ]);
                }
            }

            DB::commit();
            getProvinceIdByLatLong($createAsset);
            $this->storeAssetNerbyPlace($createAsset);

            return responseJson(Response::CREATED, (object) ["uuid" => $createAsset->uuid]);
        } catch (\Exception $exception) {
            \Log::error($exception);
            DB::rollBack();

            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    public function update($uuid)
    {
        try {
            DB::beginTransaction();

            $request = Request::all();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) {
                return responseJson(Response::NOTFOUND);
            }

            $validatorMessages = $this->createAndUpdateValidator($request);
            if ($validatorMessages) {
                return responseJson(Response::VALIDATE, $validatorMessages);
            }

            $data = [
                'ref_announcer_status_id' => $request['ref_announcer_status_id'],
                'ref_announcement_type_id' => $request['ref_announcement_type_id'],
                'ref_asset_type_id' => $request['ref_asset_type_id'],
                'ref_location_id' => $request['ref_location_id'],
                'contact_phone' => isset($request['contact_phone']) ? $request['contact_phone'] : null,
                'contact_line' => isset($request['contact_line']) ? $request['contact_line'] : null,
                'latitude' => isset($request['latitude']) ? $request['latitude'] : null,
                'longitude' => isset($request['longitude']) ? $request['longitude'] : null,
                'updated_by' => isset(Auth::user()->id) ? Auth::user()->id : null,
                'updated_at' => Carbon::now(),
            ];

            $updateAsset = $asset->update($data);
            if (!$updateAsset) {
                return responseJson(Response::FAIL);
            }

            $oldAssetPriceRents = AssetPriceRent::getAssetPriceRents()->where('asset_id', $asset->id)->pluck('price', 'ref_type_rent_id');
            DB::table('asset_price_rent')->where('asset_id', $asset->id)->delete();
            if ($request['ref_announcement_type_id'] == RefAnnouncementType::ForRent) {
                $refTypeRents = RefTypeRent::getRefTypeRents()->get();
                foreach ($refTypeRents as $refTypeRent) {
                    AssetPriceRent::create([
                        'asset_id' => $asset->id,
                        'ref_type_rent_id' => $refTypeRent->id,
                        'price' => isset($oldAssetPriceRents[$refTypeRent->id]) ? $oldAssetPriceRents[$refTypeRent->id] : null,
                    ]);
                }
            }

            DB::commit();
            getProvinceIdByLatLong($asset);
            $this->storeAssetNerbyPlace($asset);

            return responseJson(Response::ACCEPTED);
        } catch (\Exception $exception) {
            \Log::error($exception);
            DB::rollBack();

            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    public function updateInfo($uuid)
    {
        try {
            DB::beginTransaction();

            $request = Request::all();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) {
                return responseJson(Response::NOTFOUND);
            }

            $validatorMessages = $this->updateInfoValidator($request, $asset);
            if ($validatorMessages) {
                return responseJson(Response::VALIDATE, $validatorMessages);
            }

            $minPrice = 0;
            if ($asset->ref_announcement_type_id == RefAnnouncementType::ForRent) {
                if (isset($request['asset_price_rents']) && is_array($request['asset_price_rents'])) {
                    $collect = collect($request['asset_price_rents']);
                    $minRefTypeRentId = $collect->where('price', '>', 0)->min('ref_type_rent_id');
                    $priceItem = $collect->where('ref_type_rent_id', $minRefTypeRentId)->first();
                    $minPrice = isset($priceItem['price']) ? $priceItem['price'] : 0;
                }
            }

            $data = [
                'no' => $request['no'] ?? $asset->no,
                'name_th' => $request['name_th'],
                'title_th' => $request['title_th'],
                'description_th' => $request['description_th'],
                'bathroom_quantity' => $request['bathroom_quantity'],
                'bedroom_quantity' => $request['bedroom_quantity'],
                'floor_quantity' => $request['floor_quantity'],
                'usable_area' => $request['usable_area'],
                'price_before_discount' => ($asset->ref_announcement_type_id == 2) ? 0 : ($request['price_before_discount'] ?? 0),
                'price' => ($asset->ref_announcement_type_id == 2) ? $minPrice : ($request['price'] ?? 0),
                'cover_img_id' => $request['cover_img_id'],
                'is_pet_friendly' => $request['is_pet_friendly'] ?? 0,
                'updated_by' => isset(Auth::user()->id) ? Auth::user()->id : null,
                'updated_at' => Carbon::now(),
            ];
            $updateAsset = $asset->update($data);
            if (!$updateAsset) {
                return responseJson(Response::FAIL);
            }

            DB::table('asset_special_feature')->where('asset_id', $asset->id)->delete();
            if (isset($request['asset_special_feature_ids']) && is_array($request['asset_special_feature_ids'])) {
                foreach ($request['asset_special_feature_ids'] as $asset_special_feature_id) {
                    AssetSpecialFeature::create([
                        'asset_id' => $asset->id,
                        'ref_special_feature_id' => $asset_special_feature_id,
                    ]);
                }
            }

            DB::table('asset_image')->where('asset_id', $asset->id)->delete();
            if (isset($request['asset_image_ids']) && is_array($request['asset_image_ids'])) {
                foreach ($request['asset_image_ids'] as $key => $asset_image_id) {
                    AssetImage::create([
                        'asset_id' => $asset->id,
                        'file_storage_id' => $asset_image_id,
                        'order' => $key + 1,
                    ]);
                }
            }

            if (isset($request['asset_price_rents']) && is_array($request['asset_price_rents'])) {
                foreach ($request['asset_price_rents'] as $assetPriceRent) {
                    $assetPriceRentData = AssetPriceRent::where('asset_id', $asset->id)
                        ->where('ref_type_rent_id', $assetPriceRent['ref_type_rent_id'])
                        ->where('is_active', true)
                        ->first();
                    if ($assetPriceRentData) {
                        $assetPriceRentData->update(['price' => isset($assetPriceRent['price']) ? $assetPriceRent['price'] : null]);
                    }
                }
            }

            DB::commit();
            getProvinceIdByLatLong($asset);
            $this->storeAssetNerbyPlace($asset);

            return responseJson(Response::ACCEPTED);
        } catch (\Exception $exception) {
            \Log::error($exception);
            DB::rollBack();

            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }
    public function updateStatus($uuid)
    {
        try {
            DB::beginTransaction();

            $request = Request::all();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) {
                return responseJson(Response::NOTFOUND);
            }

            $validatorMessages = $this->updateStatusValidator($request);
            if ($validatorMessages) {
                return responseJson(Response::VALIDATE, $validatorMessages);
            }

            $asset->update([
                'ref_asset_status_id' => $request['ref_asset_status_id'],
                'updated_by' => isset(Auth::user()->id) ? Auth::user()->id : null,
                'updated_at' => Carbon::now(),
            ]);

            DB::commit();

            return responseJson(Response::ACCEPTED);
        } catch (\Exception $exception) {
            \Log::error($exception);
            DB::rollBack();

            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }
    public function delete($uuid)
    {
        try {
            DB::beginTransaction();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) {
                return responseJson(Response::NOTFOUND);
            }

            $asset->update(['is_active' => false]);
            $asset->delete();

            DB::commit();
            return responseJson(Response::DELETED);
        } catch (\Exception $exception) {
            DB::rollBack();
            \Log::error($exception);
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    private function createAndUpdateValidator($data)
    {
        $rules = [
            'ref_announcer_status_id' => 'required',
            'ref_announcement_type_id' => 'required',
            'ref_asset_type_id' => 'required',
            'ref_location_id' => 'required',
            'latitude' => 'nullable|regex:/^\\d+(\\.\\d{1,16})?$/',
            'longitude' => 'nullable|regex:/^\\d+(\\.\\d{1,16})?$/',
        ];

        return validateMessage($data, $rules);
    }

    private function updateInfoValidator($data, $asset)
    {
        $rules = [
            "name_th" => 'required',
            "title_th" => 'required',
            "description_th" => 'required',
            "bathroom_quantity" => 'required',
            "bedroom_quantity" => 'required',
            "floor_quantity" => 'required',
            "usable_area" => 'required',
            "cover_img_id" => 'required',
            "asset_image_ids" => 'required',
            "is_pet_friendly" => 'required',
        ];

        if ($asset->ref_announcement_type_id && $asset->ref_announcement_type_id == 2) {
            if (!isset($data['asset_price_rents'])) {
                $rules['asset_price_rents'] = 'required';
            }
        } else {
            $rules['price_before_discount'] = 'required';
            $rules['price'] = 'required';
        }

        return validateMessage($data, $rules);
    }

    private function storeAssetNerbyPlace($asset)
    {
        $assetNearbyPlaces = $asset->assetNearbyPlaces;
        foreach ($assetNearbyPlaces as $assetNearbyPlace) {
            $assetNearbyPlace->update(['is_active' => false]);
            $assetNearbyPlace->delete();
        }

        if ($asset->longitude && $asset->latitude) {
            $data = [];

            $refTransisStations = DB::select("SELECT * FROM ref_transis_station WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_TRANSIS_STATION', 2000) . ";");
            foreach ($refTransisStations as $refTransisStation) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refTransisStation->latitude;
                $lon2 = $refTransisStation->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_TRANSIS_STATION', 2000)) {
                    $data[] = [
                        'asset_id' => $asset->id,
                        'ref_table_name' => 'ref_transis_station',
                        'ref_id' => $refTransisStation->id,
                        'distance' => $distance->distance,
                    ];
                }
            }

            $refUniversities = DB::select("SELECT * FROM ref_university WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_UNIVERSTITY', 1000) . ";");
            foreach ($refUniversities as $refUniversity) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refUniversity->latitude;
                $lon2 = $refUniversity->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_UNIVERSTITY', 1000)) {
                    $data[] = [
                        'asset_id' => $asset->id,
                        'ref_table_name' => 'ref_university',
                        'ref_id' => $refUniversity->id,
                        'distance' => $distance->distance,
                    ];
                }
            }

            $refAirports = DB::select("SELECT * FROM ref_airport WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_AIRPORT', 10000) . ";");
            foreach ($refAirports as $refAirport) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refAirport->latitude;
                $lon2 = $refAirport->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_AIRPORT', 10000)) {
                    $data[] = [
                        'asset_id' => $asset->id,
                        'ref_table_name' => 'ref_airport',
                        'ref_id' => $refAirport->id,
                        'distance' => $distance->distance,
                    ];
                }
            }

            $refMalls = DB::select("SELECT * FROM ref_mall WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_MALL', 5000) . ";");
            foreach ($refMalls as $refMall) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refMall->latitude;
                $lon2 = $refMall->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_MALL', 5000)) {
                    $data[] = [
                        'asset_id' => $asset->id,
                        'ref_table_name' => 'ref_mall',
                        'ref_id' => $refMall->id,
                        'distance' => $distance->distance,
                    ];
                }
            }

            $refHospitals = DB::select("SELECT * FROM ref_hospital WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_HOSPITAL', 5000) . ";");
            foreach ($refHospitals as $refHospital) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refHospital->latitude;
                $lon2 = $refHospital->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_HOSPITAL', 5000)) {
                    $data[] = [
                        'asset_id' => $asset->id,
                        'ref_table_name' => 'ref_hospital',
                        'ref_id' => $refHospital->id,
                        'distance' => $distance->distance,
                    ];
                }
            }

            $asset->assetNearbyPlaces()->createMany($data);
        }

        return true;
    }
    public function searchLocation(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();

            $data = RefLocation::select(
                'ref_location.*',
                'ref_district.id as ref_district_id',
                'ref_district.name_th as ref_district_name_th',
                'ref_district.name_en as ref_district_name_en',
                'ref_province.id as ref_province_id',
                'ref_province.name_th as ref_province_name_th',
                'ref_province.name_en as ref_province_name_en'
            )
                ->join('ref_district', 'ref_district.id', '=', 'ref_location.ref_district_id')
                ->join('ref_province', 'ref_province.id', '=', 'ref_location.ref_province_id');

            if ($request->search) {
                $keyword = strtolower($request->search);
                $data->whereRaw(
                    '(LOWER(ref_location.name_th) LIKE ? OR LOWER(ref_location.name_en) LIKE ?)',
                    ['%' . $keyword . '%', '%' . $keyword . '%']
                );
            }

            $data = $data->where('ref_location.is_active', true)->limit(100);

            return responsePaginate(Datatables::of($data)
                ->addColumn('ref_district', function ($item) {
                    return (object) [
                        "id" => $item->ref_district_id,
                        "name_th" => $item->ref_district_name_th,
                        "name_en" => $item->ref_district_name_en,
                    ];
                })
                ->addColumn('ref_province', function ($item) {
                    return (object) [
                        "id" => $item->ref_province_id,
                        "name_th" => $item->ref_province_name_th,
                        "name_en" => $item->ref_province_name_en,
                    ];
                })
                ->removeColumn([
                    'ref_district_id',
                    'ref_district_name_th',
                    'ref_district_name_en',
                    'ref_province_id',
                    'ref_province_name_th',
                    'ref_province_name_en',
                    'is_active',
                    'created_by',
                    'updated_by',
                    'created_at',
                    'updated_at',
                    'deleted_at',
                ])
                ->make(true));
        } catch (\Exception $exception) {
            \Log::error($exception);
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }
    public function export()
    {
        try {
            $request = Request::all();
            $exportPath = 'exports/assets';
            $fullPath = storage_path('app/public/' . $exportPath);
            if (!file_exists($fullPath)) {
                mkdir($fullPath, 0777, true);
            }
            $filename = 'asset_export_' . date('Ymd_His') . '.xlsx';
            $filePath = $exportPath . '/' . $filename;
            \Maatwebsite\Excel\Facades\Excel::store(
                new \App\Exports\AssetExport($request),
                $filePath,
                'public'
            );
            $url = url('storage/' . $filePath);
            return responseJson(Response::SUCCESS, ['url' => $url]);
        } catch (\Exception $exception) {
            \Log::error($exception);
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }
}
