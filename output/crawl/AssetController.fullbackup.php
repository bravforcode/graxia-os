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
    function __construct()
    {
        ini_set('max_execution_time', '600');
    }

    public function list(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();

            $data = Asset::select(
                'asset.id', 'asset.uuid', 'asset.no', 'asset.created_at', 'asset.created_by',
                'asset.updated_at', 'asset.updated_by', 'asset.ref_announcer_status_id',
                'asset.ref_announcement_type_id', 'asset.ref_asset_type_id', 'asset.ref_location_id',
                'asset.name_th', 'asset.title_th', 'asset.bathroom_quantity', 'asset.bedroom_quantity',
                'asset.floor_quantity', 'asset.usable_area', 'asset.price_before_discount',
                'asset.price', 'asset.ref_asset_status_id', 'asset.latitude', 'asset.longitude',
                'asset.cover_img_id', 'ref_location.name_th as ref_location_name_th',
                'ref_location.name_en as ref_location_name_en'
            )
                ->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id')
                ->where('asset.ref_asset_status_id', 2);

            if (!$request->sort_by || !$request->sort_type) {
                $data->orderBy('asset.updated_at', 'desc');
            } else if ($request->sort_type && $request->sort_by) {
                $data->orderBy($request->sort_by, $request->sort_type);
            }

            if ($request->search) {
                $arrayAssetIds = [];

                $refTransisStationIds = RefTransisStation::select('id')->whereRaw('LOWER(name_th) LIKE ?', [strtolower($request->search) . '%'])->pluck('id')->toArray();
                $assetIds = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_transis_station')->whereIn('ref_id', $refTransisStationIds)->pluck('asset_id')->toArray();
                $arrayAssetIds = array_merge($arrayAssetIds, $assetIds);

                $refUniversityIds = RefUniversity::select('id')->whereRaw('LOWER(name_th) LIKE ?', [strtolower($request->search) . '%'])->pluck('id')->toArray();
                $assetIds = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_university')->whereIn('ref_id', $refUniversityIds)->pluck('asset_id')->toArray();
                $arrayAssetIds = array_merge($arrayAssetIds, $assetIds);

                $refAirportIds = RefAirport::select('id')->whereRaw('LOWER(name_th) LIKE ?', [strtolower($request->search) . '%'])->pluck('id')->toArray();
                $assetIds = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_airport')->whereIn('ref_id', $refAirportIds)->pluck('asset_id')->toArray();
                $arrayAssetIds = array_merge($arrayAssetIds, $assetIds);

                $refMallIds = RefMall::select('id')->whereRaw('LOWER(name_th) LIKE ?', [strtolower($request->search) . '%'])->pluck('id')->toArray();
                $assetIds = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_mall')->whereIn('ref_id', $refMallIds)->pluck('asset_id')->toArray();
                $arrayAssetIds = array_merge($arrayAssetIds, $assetIds);

                $refHospitalIds = RefHospital::select('id')->whereRaw('LOWER(name_th) LIKE ?', [strtolower($request->search) . '%'])->pluck('id')->toArray();
                $assetIds = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_hospital')->whereIn('ref_id', $refHospitalIds)->pluck('asset_id')->toArray();
                $arrayAssetIds = array_merge($arrayAssetIds, $assetIds);

                $arrayAssetIds = array_unique($arrayAssetIds);

                $html = '';
                if (count($arrayAssetIds) != 0) {
                    $html = 'OR asset.id IN (' . implode(",", $arrayAssetIds) . ')';
                }

                $data->whereRaw(
                    '(LOWER(asset.name_th) LIKE ? OR LOWER(ref_location.name_th) LIKE ? OR LOWER(asset.title_th) LIKE ? OR LOWER(asset.no) LIKE ?) ' . $html,
                    ['%' . strtolower($request->search) . '%', '%' . strtolower($request->search) . '%', '%' . strtolower($request->search) . '%', '%' . strtolower($request->search) . '%']
                );
            }

            if ($request->ref_asset_type_id) $data->where('asset.ref_asset_type_id', $request->ref_asset_type_id);
            if ($request->ref_announcement_type_id) $data->where('asset.ref_announcement_type_id', $request->ref_announcement_type_id);
            
            if ($request->ref_price_range_id) {
                $refPriceRange = RefPriceRange::getRefPriceRanges()->where('id', $request->ref_price_range_id)->first();
                $condition = getConditionStartEnd($refPriceRange);
                if ($condition['start'] != null) $data->where('asset.price', $condition['start']['operator'], $condition['start']['number']);
                if ($condition['end'] != null) $data->where('asset.price', $condition['end']['operator'], $condition['end']['number']);
            }

            if ($request->ref_room_range_id) {
                $refRoomRange = RefRoomRange::getRefRoomRanges()->where('id', $request->ref_room_range_id)->first();
                $condition = getConditionStartEnd($refRoomRange);
                if ($condition['start'] != null) $data->where('asset.bedroom_quantity', $condition['start']['operator'], $condition['start']['number']);
                if ($condition['end'] != null) $data->where('asset.bedroom_quantity', $condition['end']['operator'], $condition['end']['number']);
            }

            if ($request->ref_usable_area_range_id) {
                $refUsableAreaRange = RefUsableAreaRange::getRefUsableAreaRanges()->where('id', $request->ref_usable_area_range_id)->first();
                $condition = getConditionStartEnd($refUsableAreaRange);
                if ($condition['start'] != null) $data->where('asset.usable_area', $condition['start']['operator'], $condition['start']['number']);
                if ($condition['end'] != null) $data->where('asset.usable_area', $condition['end']['operator'], $condition['end']['number']);
            }

            if ($request->ref_special_feature_ids && $request->ref_special_feature_ids != "[]") {
                $dataAssetSpecialFeature = [];
                $arrayRefSpecialFeatureIds = json_decode($request->ref_special_feature_ids);
                foreach ($arrayRefSpecialFeatureIds as $key => $arrayRefSpecialFeatureId) {
                    $assetSpecialFeatures = AssetSpecialFeature::getAssetSpecialFeatures()->where('ref_special_feature_id', $arrayRefSpecialFeatureId)->get();
                    foreach ($assetSpecialFeatures as $key => $assetSpecialFeature) {
                        if (isset($dataAssetSpecialFeature[$assetSpecialFeature->asset_id])) {
                            $dataAssetSpecialFeature[$assetSpecialFeature->asset_id] += 1;
                        } else {
                            $dataAssetSpecialFeature[$assetSpecialFeature->asset_id] = 1;
                        }
                    }
                }
                $assetIds = [];
                foreach ($dataAssetSpecialFeature as $key => $item) {
                    if ($item == count($arrayRefSpecialFeatureIds)) $assetIds[] = $key;
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
                                $query->whereNull('asset.updated_by')->where('asset.created_by', $request->created_by);
                            });
                    });
                }
            }

            if ($request->ref_asset_type_other_id && $request->ref_asset_type_other_id != "[]") {
                $arrayRefAssetTypeOtherIds  = json_decode($request->ref_asset_type_other_id);
                foreach ($arrayRefAssetTypeOtherIds as $key => $arrayRefAssetTypeOtherId) {
                    switch ($arrayRefAssetTypeOtherId) {
                        case '1': $data->where('asset.ref_announcer_status_id', 1); break;
                        case '2':
                            $assetNearbyPlaces = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_transis_station')->where('distance', '<=', '2000')->get();
                            $arrayAssetNearbyPlaceIds = [];
                            foreach ($assetNearbyPlaces as $key => $assetNearbyPlace) { $arrayAssetNearbyPlaceIds[] = $assetNearbyPlace->asset_id; }
                            $data->whereIn('asset.id', $arrayAssetNearbyPlaceIds);
                            break;
                        case '3':
                            $assetNearbyPlaces = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_university')->where('distance', '<=', '1000')->get();
                            $arrayAssetNearbyPlaceIds = [];
                            foreach ($assetNearbyPlaces as $key => $assetNearbyPlace) { $arrayAssetNearbyPlaceIds[] = $assetNearbyPlace->asset_id; }
                            $data->whereIn('asset.id', $arrayAssetNearbyPlaceIds);
                            break;
                        case '4': $data->where('asset.is_pet_friendly', 1); break;
                        case '5':
                            $assetPriceRents = AssetPriceRent::getAssetPriceRents()->select('asset_id')->where('ref_type_rent_id', 1)->where('price', '>', 0)->get();
                            $arrayAssetPriceRentIds = [];
                            foreach ($assetPriceRents as $key => $assetPriceRent) { $arrayAssetPriceRentIds[] = $assetPriceRent->asset_id; }
                            $data->whereIn('asset.id', $arrayAssetPriceRentIds);
                            break;
                        case '6': $data->where('asset.ref_announcement_type_id', 3); break;
                    }
                }
            }

            $data = $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($query) use ($request) { $request = mergePaginate($request); })
                ->editColumn('created_by', function ($item) {
                    $userRaw = $item->created_by ? User::getUserById($item->created_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    if ($user) {
                        $objUserRoles = [];
                        $userHasRole = $user->userHasRole()->where('is_active', true)->first();
                        if ($userHasRole) {
                            $objUserRoles = ["id" => $userHasRole->role->id, "name" => $userHasRole->role->name];
                        }
                        return (object)[
                            "id"            => $user->id,
                            "full_name_th"  => $user->fullnameth ?? $user->full_name_th ?? '',
                            "full_name_en"  => $user->fullnameen ?? $user->full_name_en ?? '',
                            "role"          => $objUserRoles
                        ];
                    }
                    return (object)["id" => "0", "full_name_th" => "Anonymous", "full_name_en" => "Anonymous", "role" => (object)[]];
                })
                ->editColumn('updated_by', function ($item) {
                    $userRaw = $item->updated_by ? User::getUserById($item->updated_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    if ($user) {
                        $objUserRoles = [];
                        $userHasRole = $user->userHasRole()->where('is_active', true)->first();
                        if ($userHasRole) {
                            $objUserRoles = ["id" => $userHasRole->role->id, "name" => $userHasRole->role->name];
                        }
                        return (object)[
                            "id"            => $user->id,
                            "full_name_th"  => $user->fullnameth ?? $user->full_name_th ?? '',
                            "full_name_en"  => $user->fullnameen ?? $user->full_name_en ?? '',
                            "role"          => $objUserRoles
                        ];
                    }
                    return (object)["id" => "0", "full_name_th" => "Anonymous", "full_name_en" => "Anonymous", "role" => (object)[]];
                })
                ->addColumn('ref_announcer_status', function ($item) {
                    $ref = $item->refAnnouncerStatus()->select('id', 'name_th', 'name_en')->first();
                    return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null;
                })
                ->addColumn('ref_announcement_type', function ($item) {
                    $ref = $item->refAnnouncementType()->select('id', 'name_th', 'name_en')->first();
                    return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null;
                })
                ->addColumn('ref_asset_type', function ($item) {
                    $ref = $item->refAssetType()->select('id', 'name_th', 'name_en')->first();
                    return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null;
                })
                ->addColumn('ref_location', function ($item) {
                    $refLocation = RefLocation::getRefLocations()->where('id', $item->ref_location_id)->first();
                    if ($refLocation) {
                        $refDistrict = RefDistrict::getRefDistricts()->where('id', $refLocation->ref_district_id)->first();
                        $refProvince = RefProvince::getRefProvinces()->where('id', $refLocation->ref_province_id)->first();
                        return (object)[
                            "id"            => $refLocation->id,
                            "name_th"       => $refLocation->name_th,
                            "name_en"       => $refLocation->name_en,
                            "ref_district"  => $refDistrict ? (object)["id" => $refDistrict->id, "name_th" => $refDistrict->name_th, "name_en" => $refDistrict->name_en] : (object)[],
                            "ref_province"  => $refProvince ? (object)["id" => $refProvince->id, "name_th" => $refProvince->name_th, "name_en" => $refProvince->name_en] : (object)[],
                            "latitude"      => $refLocation->latitude,
                            "longitude"     => $refLocation->longitude,
                        ];
                    }
                    return null;
                })
                ->addColumn('ref_asset_status', function ($item) {
                    $ref = $item->refAssetStatus()->select('id', 'name_th', 'name_en', 'color_code')->first();
                    return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en, "color_code" => $ref->color_code] : null;
                })
                ->addColumn('cover_img', function ($item) {
                    $img = FileStorage::where('id', $item->cover_img_id)->first();
                    return $img ? (object)[
                        "id"    => $img->id, "name"  => $img->file_name, "size"  => $img->file_size,
                        "type"  => $img->file_type, "ext"   => str_replace('image/', '', $img->file_type),
                        "url"   => url($img->file_path . '/' . $img->file_name)
                    ] : null;
                })
                ->removeColumn(['ref_announcer_status_id', 'ref_announcement_type_id', 'ref_asset_type_id', 'ref_location_id', 'ref_asset_status_id', 'cover_img_id', 'ref_location_name_th', 'ref_location_name_en'])
                ->make(true));
        } catch (\Exception $exception) {
            \Log::error($exception);
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    public function listOwner(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();
            $data = Asset::select('asset.*')->where('asset.ref_announcer_status_id', 1)->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id');
            if (!$request->sort_by || !$request->sort_type) { $data->orderBy('asset.created_at', 'asc'); } else if ($request->sort_type && $request->sort_by) { $data->orderBy($request->sort_by, $request->sort_type); }
            $data = $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($query) use ($request) { $request = mergePaginate($request); })
                ->editColumn('created_by', function ($item) {
                    $userRaw = $item->created_by ? User::getUserById($item->created_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? '', "full_name_en" => $user->fullnameen ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous", "full_name_en" => "Anonymous"];
                })
                ->editColumn('updated_by', function ($item) {
                    $userRaw = $item->updated_by ? User::getUserById($item->updated_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? '', "full_name_en" => $user->fullnameen ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous", "full_name_en" => "Anonymous"];
                })
                ->addColumn('ref_announcer_status', function ($item) { $ref = $item->refAnnouncerStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_announcement_type', function ($item) { $ref = $item->refAnnouncementType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_asset_type', function ($item) { $ref = $item->refAssetType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_location', function ($item) { $ref = RefLocation::getRefLocations()->where('id', $item->ref_location_id)->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_asset_status', function ($item) { $ref = $item->refAssetStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en, "color_code" => $ref->color_code] : null; })
                ->addColumn('cover_img', function ($item) { $img = FileStorage::where('id', $item->cover_img_id)->first(); return $img ? (object)["id" => $img->id, "name" => $img->file_name, "url" => url($img->file_path . '/' . $img->file_name)] : null; })
                ->make(true));
        } catch (\Exception $exception) { return responseJson(Response::ERROR, $exception->getMessage()); }
    }

    public function listNearbyTransis(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();
            $data = Asset::select('asset.*')->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id');
            if (!$request->sort_by || !$request->sort_type) { $data->orderBy('asset.created_at', 'asc'); } else if ($request->sort_type && $request->sort_by) { $data->orderBy($request->sort_by, $request->sort_type); }

            $assetNearbyPlaces = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_transis_station')->where('distance', '<=', '2000')->get();
            $arrayAssetNearbyPlaceIds = [];
            foreach ($assetNearbyPlaces as $key => $assetNearbyPlace) { $arrayAssetNearbyPlaceIds[] = $assetNearbyPlace->asset_id; }
            $data->whereIn('asset.id', $arrayAssetNearbyPlaceIds);
            $data = $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($query) use ($request) { $request = mergePaginate($request); })
                ->editColumn('created_by', function ($item) {
                    $userRaw = $item->created_by ? User::getUserById($item->created_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? '', "full_name_en" => $user->fullnameen ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous", "full_name_en" => "Anonymous"];
                })
                ->editColumn('updated_by', function ($item) {
                    $userRaw = $item->updated_by ? User::getUserById($item->updated_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? '', "full_name_en" => $user->fullnameen ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous", "full_name_en" => "Anonymous"];
                })
                ->addColumn('ref_announcer_status', function ($item) { $ref = $item->refAnnouncerStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_announcement_type', function ($item) { $ref = $item->refAnnouncementType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_asset_type', function ($item) { $ref = $item->refAssetType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en] : null; })
                ->addColumn('ref_asset_status', function ($item) { $ref = $item->refAssetStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "name_en" => $ref->name_en, "color_code" => $ref->color_code] : null; })
                ->addColumn('cover_img', function ($item) { $img = FileStorage::where('id', $item->cover_img_id)->first(); return $img ? (object)["id" => $img->id, "name" => $img->file_name, "url" => url($img->file_path . '/' . $img->file_name)] : null; })
                ->make(true));
        } catch (\Exception $exception) { return responseJson(Response::ERROR, $exception->getMessage()); }
    }

    public function listPetFriendly(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();
            $data = Asset::select('asset.*')->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id');
            if (!$request->sort_by || !$request->sort_type) { $data->orderBy('asset.created_at', 'asc'); } else if ($request->sort_type && $request->sort_by) { $data->orderBy($request->sort_by, $request->sort_type); }

            $data->where('asset.is_pet_friendly', 1);
            $data = $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($query) use ($request) { $request = mergePaginate($request); })
                ->editColumn('created_by', function ($item) {
                    $userRaw = $item->created_by ? User::getUserById($item->created_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous"];
                })
                ->editColumn('updated_by', function ($item) {
                    $userRaw = $item->updated_by ? User::getUserById($item->updated_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous"];
                })
                ->addColumn('ref_announcer_status', function ($item) { $ref = $item->refAnnouncerStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_announcement_type', function ($item) { $ref = $item->refAnnouncementType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_asset_type', function ($item) { $ref = $item->refAssetType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_asset_status', function ($item) { $ref = $item->refAssetStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "color_code" => $ref->color_code] : null; })
                ->addColumn('cover_img', function ($item) { $img = FileStorage::where('id', $item->cover_img_id)->first(); return $img ? (object)["id" => $img->id, "name" => $img->file_name, "url" => url($img->file_path . '/' . $img->file_name)] : null; })
                ->make(true));
        } catch (\Exception $exception) { return responseJson(Response::ERROR, $exception->getMessage()); }
    }

    public function listShortTerm(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();
            $data = Asset::select('asset.*')->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id');
            if (!$request->sort_by || !$request->sort_type) { $data->orderBy('asset.created_at', 'asc'); } else if ($request->sort_type && $request->sort_by) { $data->orderBy($request->sort_by, $request->sort_type); }

            $assetPriceRents = AssetPriceRent::getAssetPriceRents()->select('asset_id')->where('ref_type_rent_id', 1)->get();
            $arrayAssetPriceRentIds = [];
            foreach ($assetPriceRents as $key => $assetPriceRent) { $arrayAssetPriceRentIds[] = $assetPriceRent->asset_id; }
            $data->whereIn('asset.id', $arrayAssetPriceRentIds);
            $data = $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($query) use ($request) { $request = mergePaginate($request); })
                ->editColumn('created_by', function ($item) {
                    $userRaw = $item->created_by ? User::getUserById($item->created_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous"];
                })
                ->editColumn('updated_by', function ($item) {
                    $userRaw = $item->updated_by ? User::getUserById($item->updated_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous"];
                })
                ->addColumn('ref_announcer_status', function ($item) { $ref = $item->refAnnouncerStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_announcement_type', function ($item) { $ref = $item->refAnnouncementType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_asset_type', function ($item) { $ref = $item->refAssetType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_asset_status', function ($item) { $ref = $item->refAssetStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "color_code" => $ref->color_code] : null; })
                ->addColumn('cover_img', function ($item) { $img = FileStorage::where('id', $item->cover_img_id)->first(); return $img ? (object)["id" => $img->id, "name" => $img->file_name, "url" => url($img->file_path . '/' . $img->file_name)] : null; })
                ->make(true));
        } catch (\Exception $exception) { return responseJson(Response::ERROR, $exception->getMessage()); }
    }

    public function listNearbyUniversity(Datatables $datatables)
    {
        try {
            $request = $datatables->getRequest();
            $data = Asset::select('asset.*')->leftjoin('ref_location', 'asset.ref_location_id', '=', 'ref_location.id');
            if (!$request->sort_by || !$request->sort_type) { $data->orderBy('asset.created_at', 'asc'); } else if ($request->sort_type && $request->sort_by) { $data->orderBy($request->sort_by, $request->sort_type); }

            $assetNearbyPlaces = AssetNearbyPlace::getAssetNearbyPlaces()->select('asset_id')->where('ref_table_name', 'ref_university')->where('distance', '<=', '1000')->get();
            $arrayAssetNearbyPlaceIds = [];
            foreach ($assetNearbyPlaces as $key => $assetNearbyPlace) { $arrayAssetNearbyPlaceIds[] = $assetNearbyPlace->asset_id; }
            $data->whereIn('asset.id', $arrayAssetNearbyPlaceIds);
            $data = $data->where('asset.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->filter(function ($query) use ($request) { $request = mergePaginate($request); })
                ->editColumn('created_by', function ($item) {
                    $userRaw = $item->created_by ? User::getUserById($item->created_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous"];
                })
                ->editColumn('updated_by', function ($item) {
                    $userRaw = $item->updated_by ? User::getUserById($item->updated_by) : null;
                    $user = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
                    return $user ? (object)["id" => $user->id, "full_name_th" => $user->fullnameth ?? ''] : (object)["id" => "0", "full_name_th" => "Anonymous"];
                })
                ->addColumn('ref_announcer_status', function ($item) { $ref = $item->refAnnouncerStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_announcement_type', function ($item) { $ref = $item->refAnnouncementType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_asset_type', function ($item) { $ref = $item->refAssetType()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th] : null; })
                ->addColumn('ref_asset_status', function ($item) { $ref = $item->refAssetStatus()->first(); return $ref ? (object)["id" => $ref->id, "name_th" => $ref->name_th, "color_code" => $ref->color_code] : null; })
                ->addColumn('cover_img', function ($item) { $img = FileStorage::where('id', $item->cover_img_id)->first(); return $img ? (object)["id" => $img->id, "name" => $img->file_name, "url" => url($img->file_path . '/' . $img->file_name)] : null; })
                ->make(true));
        } catch (\Exception $exception) { return responseJson(Response::ERROR, $exception->getMessage()); }
    }

    public function data($uuid)
    {
        try {
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) {
                return responseJson(Response::NOTFOUND);
            }

            /* created_by fullname (ดัก Collection พัง) */
            $userCreated = null;
            $createdBy = [];
            if ($asset->created_by) {
                $userRaw = User::getUserById($asset->created_by);
                $userCreated = $userRaw instanceof \Illuminate\Support\Collection ? $userRaw->first() : $userRaw;
            }
            if ($userCreated) {
                $createdBy =  [
                    "id"            => $userCreated->id ?? null,
                    "full_name_th"  => $userCreated->fullnameth ?? $userCreated->full_name_th ?? '',
                    "full_name_en"  => $userCreated->fullnameen ?? $userCreated->full_name_en ?? '',
                ];
            } else {
                $createdBy =  [
                    "id"            => "0",
                    "full_name_th"  => "Anonymous",
                    "full_name_en"  => "Anonymous",
                ];
            }

            /* updated_by fullname (ดัก Collection พัง) */
            $userUpdated = null;
            $updatedBy = [];
            if ($asset->updated_by) {
                $userRaw2 = User::getUserById($asset->updated_by);
                $userUpdated = $userRaw2 instanceof \Illuminate\Support\Collection ? $userRaw2->first() : $userRaw2;
            }
            if ($userUpdated) {
                $updatedBy =  [
                    "id"            => $userUpdated->id ?? null,
                    "full_name_th"  => $userUpdated->fullnameth ?? $userUpdated->full_name_th ?? '',
                    "full_name_en"  => $userUpdated->fullnameen ?? $userUpdated->full_name_en ?? '',
                ];
            } else {
                $updatedBy =  [
                    "id"            => "0",
                    "full_name_th"  => "Anonymous",
                    "full_name_en"  => "Anonymous",
                ];
            }

            $refAnnouncerStatus = $asset->refAnnouncerStatus()->first();
            if ($refAnnouncerStatus instanceof \Illuminate\Support\Collection) $refAnnouncerStatus = $refAnnouncerStatus->first();

            $refAnnouncementType = $asset->refAnnouncementType()->first();
            if ($refAnnouncementType instanceof \Illuminate\Support\Collection) $refAnnouncementType = $refAnnouncementType->first();

            $refAssetType = $asset->refAssetType()->first();
            if ($refAssetType instanceof \Illuminate\Support\Collection) $refAssetType = $refAssetType->first();

            $refAssetStatus = $asset->refAssetStatus()->first();
            if ($refAssetStatus instanceof \Illuminate\Support\Collection) $refAssetStatus = $refAssetStatus->first();

            $refProvince = $asset->refProvince()->first();
            if ($refProvince instanceof \Illuminate\Support\Collection) $refProvince = $refProvince->first();

            $dataCoverImg = [];
            $coverImg = FileStorage::where('id', $asset->cover_img_id)->first();
            if ($coverImg) {
                $dataCoverImg = [
                    "id"    => $coverImg->id,
                    "name"  => $coverImg->file_name,
                    "size"  => $coverImg->file_size,
                    "type"  => $coverImg->file_type,
                    "ext"   => str_replace('image/', '', $coverImg->file_type),
                    "url"   => url($coverImg->file_path . '/' . $coverImg->file_name)
                ];
            }

            /* รูปภาพ */
            $assetImages = $asset->assetImages;
            $dataAssetImages = [];
            if ($assetImages) {
                foreach ($assetImages as $key => $assetImage) {
                    $img = FileStorage::where('id', $assetImage->file_storage_id)->first();
                    if ($img) {
                        $dataAssetImages[] = [
                            "id"    => $img->id,
                            "name"  => $img->file_name,
                            "size"  => $img->file_size,
                            "type"  => $img->file_type,
                            "ext"   => str_replace('image/', '', $img->file_type),
                            "url"   => url($img->file_path . '/' . $img->file_name)
                        ];
                    }
                }
            }

            /* สถานที่ใกล้เคียง */
            $assetNearbyPlaces = $asset->assetNearbyPlaces;
            $dataAssetNearbyPlaces = [];
            if ($assetNearbyPlaces) {
                foreach ($assetNearbyPlaces as $key => $assetNearbyPlace) {
                    $model = getTableNearbyPlace($assetNearbyPlace->ref_table_name);
                    if ($model) {
                        $model = $model->where('id', $assetNearbyPlace->ref_id)->first();
                        if ($model) {
                            $dataAssetNearbyPlaces[] = [
                                "id"        => $assetNearbyPlace->id,
                                "name_th"   => $model->name_th,
                                "name_en"   => $model->name_en,
                                "distance"  => round((float)$assetNearbyPlace->distance, 2),
                                "longitude" => $model->longitude,
                                "latitude"  => $model->latitude,
                                "category"  => $assetNearbyPlace->ref_table_name,
                            ];
                        }
                    }
                }
                $dataAssetNearbyPlaces = collect($dataAssetNearbyPlaces)->sortBy('distance')->values()->toArray();
            }

            /* ลักษณะพิเศษอื่น */
            $assetSpecialFeatures = $asset->assetSpecialFeatures;
            $dataAssetSpecialFeatures = [];
            if ($assetSpecialFeatures) {
                foreach ($assetSpecialFeatures as $key => $assetSpecialFeature) {
                    $refSpecial = $assetSpecialFeature->refSpecialFeature;
                    if ($refSpecial instanceof \Illuminate\Support\Collection) $refSpecial = $refSpecial->first();
                    if ($refSpecial) {
                        $dataAssetSpecialFeatures[] = [
                            "id"        => $refSpecial->id ?? null,
                            "name_th"   => $refSpecial->name_th ?? '',
                            "name_en"   => $refSpecial->name_en ?? '',
                            "img_url"   => url($refSpecial->icon ?? ''),
                        ];
                    }
                }
            }

            /* สถานที่ใกล้เคียง (Location) */
            $refLocation = RefLocation::getRefLocations()->where('id', $asset->ref_location_id)->first();
            $dataRefLocation = [];
            if ($refLocation) {
                $refDistrictData = [];
                $refDistrict = RefDistrict::getRefDistricts()->where('id', $refLocation->ref_district_id)->first();
                if ($refDistrict instanceof \Illuminate\Support\Collection) $refDistrict = $refDistrict->first();
                if ($refDistrict) {
                    $refDistrictData = [
                        "id"        => $refDistrict->id ?? null,
                        "name_th"   => $refDistrict->name_th ?? '',
                        "name_en"   => $refDistrict->name_en ?? '',
                    ];
                }

                $refProvinceData = [];
                $refProvinceDetail = RefProvince::getRefProvinces()->where('id', $refLocation->ref_province_id)->first();
                if ($refProvinceDetail instanceof \Illuminate\Support\Collection) $refProvinceDetail = $refProvinceDetail->first();
                if ($refProvinceDetail) {
                    $refProvinceData = [
                        "id"        => $refProvinceDetail->id ?? null,
                        "name_th"   => $refProvinceDetail->name_th ?? '',
                        "name_en"   => $refProvinceDetail->name_en ?? '',
                    ];
                }

                $dataRefLocation =  [
                    "id"            => $refLocation->id,
                    "name_th"       => $refLocation->name_th,
                    "name_en"       => $refLocation->name_en,
                    "ref_district"  => (object)$refDistrictData,
                    "ref_province"  => (object)$refProvinceData,
                    "latitude"      => $refLocation->latitude,
                    "longitude"     => $refLocation->longitude,
                ];
            }

            /* ข้อมูลราคาเช่า */
            $assetPriceRents = $asset->assetPriceRents;
            $dataAssetPriceRents =  [];
            if ($assetPriceRents) {
                foreach ($assetPriceRents as $key => $assetPriceRent) {
                    $refType = $assetPriceRent->refTypeRent;
                    if ($refType instanceof \Illuminate\Support\Collection) $refType = $refType->first();
                    if ($refType) {
                        $dataRefPriceRent = [
                            "id"        => $refType->id ?? null,
                            "name_th"   => $refType->name_th ?? '',
                            "name_en"   => $refType->name_en ?? '',
                        ];
                        $dataAssetPriceRents[] = [
                            "id"                => $assetPriceRent->id,
                            "ref_price_rent"    => $dataRefPriceRent,
                            "price"             => $assetPriceRent->price,
                        ];
                    }
                }
            }

            /* รถไฟฟ้าใกล้เคียง */
            $assetNearbyPlacesTransis = $asset->assetNearbyPlaces ? $asset->assetNearbyPlaces->where('ref_table_name', 'ref_transis_station') : [];
            $dataTrasisStations = [];
            foreach ($assetNearbyPlacesTransis as $key => $assetNearbyPlace) {
                $model = getTableNearbyPlace($assetNearbyPlace->ref_table_name);
                if ($model) {
                    $model = $model->where('id', $assetNearbyPlace->ref_id)->first();
                    if ($model) {
                        $dataTrasisStations[] = [
                            "id"        => $assetNearbyPlace->id,
                            "name_th"   => $model->name_th,
                            "name_en"   => $model->name_en,
                            "distance"  => round((float)$assetNearbyPlace->distance, 2),
                            "longitude" => $model->longitude,
                            "latitude"  => $model->latitude,
                            "category"  => $assetNearbyPlace->ref_table_name,
                        ];
                    }
                }
            }
            $dataTrasisStations = collect($dataTrasisStations)->sortBy('distance')->values()->toArray();

            /* === เพิ่มตัวดักกัน Nuxt พัง (ใส่ให้มีอย่างน้อย 1 ตัว) === */
            if (count($dataTrasisStations) == 0) {
                $dataTrasisStations = [[
                    "id" => 0,
                    "name_th" => "ไม่ระบุสถานี",
                    "name_en" => "N/A",
                    "distance" => 0,
                    "longitude" => "0",
                    "latitude" => "0",
                    "category" => "ref_transis_station"
                ]];
            }

            $data = [
                "id"                        => $asset->id,
                "uuid"                      => $asset->uuid,
                "no"                        => $asset->no,
                "created_at"                => $asset->created_at,
                "created_by"                => isset($createdBy['id']) ? (object)$createdBy : null,
                "updated_at"                => $asset->updated_at,
                "updated_by"                => isset($updatedBy['id']) ? (object)$updatedBy : null,
                "ref_announcer_status"  =>  [
                    "id"        => $refAnnouncerStatus?->id,
                    "name_th"   => $refAnnouncerStatus?->name_th,
                    "name_en"   => $refAnnouncerStatus?->name_en,
                ],
                "ref_announcement_type" => [
                    "id"        => $refAnnouncementType?->id,
                    "name_th"   => $refAnnouncementType?->name_th,
                    "name_en"   => $refAnnouncementType?->name_en,
                ],
                "ref_asset_type"    => [
                    "id"        => $refAssetType?->id,
                    "name_th"   => $refAssetType?->name_th,
                    "name_en"   => $refAssetType?->name_en,
                ],
                "ref_location"              => (object)$dataRefLocation,
                "contact_phone"             => $asset->contact_phone ?? null,
                "contact_line"              => $asset->contact_line ?? null,
                "name_th"                   => $asset->name_th,
                "title_th"                  => $asset->title_th,
                "description_th"            => $asset->description_th, 
                "bathroom_quantity"         => $asset->bathroom_quantity,
                "bedroom_quantity"          => $asset->bedroom_quantity,
                "floor_quantity"            => $asset->floor_quantity,
                "usable_area"               => doubleval($asset->usable_area),
                "price_before_discount"     => doubleval($asset->price_before_discount),
                "price"                     => doubleval($asset->price),
                "ref_asset_status"  => [
                    "id"            => $refAssetStatus?->id,
                    "name_th"       => $refAssetStatus?->name_th,
                    "name_en"       => $refAssetStatus?->name_en,
                    "color_code"    => $refAssetStatus?->color_code,
                ],
                "longitude"                 => $asset->longitude,
                "latitude"                  => $asset->latitude,
                "ref_province"  => [
                    "id"        => $refProvince?->id,
                    "name_th"   => $refProvince?->name_th,
                    "name_en"   => $refProvince?->name_en,
                    "longitude" => $refProvince?->longitude,
                    "latitude"  => $refProvince?->latitude,
                ],
                "asset_special_features"    => $dataAssetSpecialFeatures,
                "asset_nearby_places"       => $dataAssetNearbyPlaces,
                "cover_img"                 => empty($dataCoverImg) ? null : (object)$dataCoverImg,
                "asset_images"              => $dataAssetImages,
                "asset_price_rents"         => $dataAssetPriceRents,
                "transis_stations"          => $dataTrasisStations,
                "is_pet_friendly"           => $asset->is_pet_friendly,
            ];

            return responseJson(Response::SUCCESS, $data);
        } catch (\Exception $exception) {
            \Log::error($exception);
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    public function store()
    {
        try {
            $request = Request::all();
            $validatorMessages = $this->createAndUpdateValidator($request);
            if ($validatorMessages) return responseJson(Response::VALIDATE, $validatorMessages);

            $data = [
                'ref_announcer_status_id'   => $request['ref_announcer_status_id'],
                'ref_announcement_type_id'  => $request['ref_announcement_type_id'],
                'ref_asset_type_id'         => $request['ref_asset_type_id'],
                'ref_location_id'           => $request['ref_location_id'],
                'contact_phone'             => isset($request['contact_phone']) ? $request['contact_phone'] : null,
                'contact_line'              => isset($request['contact_line']) ? $request['contact_line'] : null,
                'latitude'                  => isset($request['latitude']) ? $request['latitude'] : null,
                'longitude'                 => isset($request['longitude']) ? $request['longitude'] : null,
                'created_by'                => isset(Auth::user()->id) ? Auth::user()->id : null,
                'created_at'                => Carbon::now(),
            ];

            $createAsset = Asset::create($data);
            if (!$createAsset) return responseJson(Response::FAIL);

            if ($request['ref_announcement_type_id'] == RefAnnouncementType::ForRent) { 
                $refTypeRents = RefTypeRent::getRefTypeRents()->get();
                foreach ($refTypeRents as $key => $refTypeRent) {
                    AssetPriceRent::create([
                        'asset_id'          => $createAsset->id,
                        'ref_type_rent_id'  => $refTypeRent->id,
                    ]);
                }
            }

            DB::commit();
            getProvinceIdByLatLong($createAsset);
            $this->storeAssetNerbyPlace($createAsset);

            return responseJson(Response::CREATED, (object)["uuid" => $createAsset->uuid]);
        } catch (\Exception $exception) {
            \Log::error($exception);
            DB::rollBack();
            return responseJson(Response::ERROR, $exception->getMessage());
        }
    }

    public function update($uuid)
    {
        try {
            $request = Request::all();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) return responseJson(Response::NOTFOUND);

            $validatorMessages = $this->createAndUpdateValidator($request);
            if ($validatorMessages) return responseJson(Response::VALIDATE, $validatorMessages);

            $data = [
                'ref_announcer_status_id'   => $request['ref_announcer_status_id'],
                'ref_announcement_type_id'  => $request['ref_announcement_type_id'],
                'ref_asset_type_id'         => $request['ref_asset_type_id'],
                'ref_location_id'           => $request['ref_location_id'],
                'contact_phone'             => isset($request['contact_phone']) ? $request['contact_phone'] : null,
                'contact_line'              => isset($request['contact_line']) ? $request['contact_line'] : null,
                'latitude'                  => isset($request['latitude']) ? $request['latitude'] : null,
                'longitude'                 => isset($request['longitude']) ? $request['longitude'] : null,
                'updated_by'                => isset(Auth::user()->id) ? Auth::user()->id : null,
                'updated_at'                => Carbon::now(),
            ];

            $updateAsset = $asset->update($data);
            if (!$updateAsset) return responseJson(Response::FAIL);

            $oldAssetPriceRents = AssetPriceRent::getAssetPriceRents()->where('asset_id', $asset->id)->pluck('price', 'ref_type_rent_id');
            DB::table('asset_price_rent')->where('asset_id', $asset->id)->delete();
            if ($request['ref_announcement_type_id'] == RefAnnouncementType::ForRent) { 
                $refTypeRents = RefTypeRent::getRefTypeRents()->get();
                foreach ($refTypeRents as $key => $refTypeRent) {
                    AssetPriceRent::create([
                        'asset_id'          => $asset->id,
                        'ref_type_rent_id'  => $refTypeRent->id,
                        'price'             => isset($oldAssetPriceRents[$refTypeRent->id]) ? $oldAssetPriceRents[$refTypeRent->id] : null,
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
            $request = Request::all();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) return responseJson(Response::NOTFOUND);

            $validatorMessages = $this->updateInfoValidator($request, $asset);
            if ($validatorMessages) return responseJson(Response::VALIDATE, $validatorMessages);

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
                'no'                        => $request['no'] ?? $asset->no,
                'name_th'                   => $request['name_th'],
                'title_th'                  => $request['title_th'],
                'description_th'            => $request['description_th'],
                'bathroom_quantity'         => $request['bathroom_quantity'],
                'bedroom_quantity'          => $request['bedroom_quantity'],
                'floor_quantity'            => $request['floor_quantity'],
                'usable_area'               => $request['usable_area'],
                'price_before_discount'     => ($asset->ref_announcement_type_id == 2) ? 0 : ($request['price_before_discount'] ?? 0),
                'price'                     => ($asset->ref_announcement_type_id == 2) ? $minPrice : ($request['price'] ?? 0),
                'cover_img_id'              => $request['cover_img_id'],
                'is_pet_friendly'           => $request['is_pet_friendly'] ?? 0,
                'updated_by'                => isset(Auth::user()->id) ? Auth::user()->id : null,
                'updated_at'                => Carbon::now(),
            ];
            $updateAsset = $asset->update($data);
            if (!$updateAsset) return responseJson(Response::FAIL);

            DB::table('asset_special_feature')->where('asset_id', $asset->id)->delete();
            if (isset($request['asset_special_feature_ids']) && is_array($request['asset_special_feature_ids'])) {
                foreach ($request['asset_special_feature_ids'] as $key => $asset_special_feature_id) {
                    AssetSpecialFeature::create([
                        'asset_id'                  => $asset->id,
                        'ref_special_feature_id'    => $asset_special_feature_id,
                    ]);
                }
            }

            DB::table('asset_image')->where('asset_id', $asset->id)->delete();
            if (isset($request['asset_image_ids']) && is_array($request['asset_image_ids'])) {
                foreach ($request['asset_image_ids'] as $key => $asset_image_id) {
                    AssetImage::create([
                        'asset_id'          => $asset->id,
                        'file_storage_id'   => $asset_image_id,
                        'order'             => $key + 1,
                    ]);
                }
            }

            if (isset($request['asset_price_rents']) && is_array($request['asset_price_rents'])) {
                foreach ($request['asset_price_rents'] as $key => $assetPriceRent) {
                    $assetPriceRentData = AssetPriceRent::where('asset_id', $asset->id)->where('ref_type_rent_id', $assetPriceRent['ref_type_rent_id'])->where('is_active', true)->first();
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
            $request = Request::all();
            $asset = Asset::where('uuid', $uuid)->where('is_active', true)->first();
            if (!$asset) return responseJson(Response::NOTFOUND);

            $validatorMessages = $this->updateStatusValidator($request);
            if ($validatorMessages) return responseJson(Response::VALIDATE, $validatorMessages);

            $asset->update([
                'ref_asset_status_id'   => $request['ref_asset_status_id'],
                'updated_by'            => isset(Auth::user()->id) ? Auth::user()->id : null,
                'updated_at'            => Carbon::now(),
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
            if (!$asset) return responseJson(Response::NOTFOUND);

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
            'ref_announcer_status_id'   => 'required',
            'ref_announcement_type_id'  => 'required',
            'ref_asset_type_id'         => 'required',
            'ref_location_id'           => 'required',
            'latitude'                  => 'nullable|regex:/^\d+(\.\d{1,16})?$/',
            'longitude'                 => 'nullable|regex:/^\d+(\.\d{1,16})?$/',
        ];
        return validateMessage($data, $rules);
    }

    private function updateInfoValidator($data, $asset)
    {
        $rules = [
            "name_th"                   => 'required',
            "title_th"                  => 'required',
            "description_th"            => 'required',
            "bathroom_quantity"         => 'required',
            "bedroom_quantity"          => 'required',
            "floor_quantity"            => 'required',
            "usable_area"               => 'required',
            "cover_img_id"              => 'required',
            "asset_image_ids"           => 'required',
            "is_pet_friendly"           => 'required',
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

    private function updateStatusValidator($data)
    {
        $rules = [
            "ref_asset_status_id"   => 'required',
        ];
        return validateMessage($data, $rules);
    }

    private function storeAssetNerbyPlace($asset)
    {
        $assetNearbyPlaces = $asset->assetNearbyPlaces;
        foreach ($assetNearbyPlaces as $key => $assetNearbyPlace) {
            $assetNearbyPlace->update(['is_active' => false]);
            $assetNearbyPlace->delete();
        }

        if ($asset->longitude && $asset->latitude) {
            $data = [];
            
            $refTransisStations = DB::select("SELECT * FROM ref_transis_station WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_TRANSIS_STATION', 2000) . ";");
            foreach ($refTransisStations as $key => $refTransisStation) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refTransisStation->latitude;
                $lon2 = $refTransisStation->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_TRANSIS_STATION', 2000))
                    $data[] = [
                        'asset_id'          => $asset->id,
                        'ref_table_name'    => 'ref_transis_station',
                        'ref_id'            => $refTransisStation->id,
                        'distance'          => $distance->distance,
                    ];
            }

            $refUniversities = DB::select("SELECT * FROM ref_university WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_UNIVERSTITY', 1000) . ";");
            foreach ($refUniversities as $key => $refUniversity) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refUniversity->latitude;
                $lon2 = $refUniversity->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_UNIVERSTITY', 1000))
                    $data[] = [
                        'asset_id'          => $asset->id,
                        'ref_table_name'    => 'ref_university',
                        'ref_id'            => $refUniversity->id,
                        'distance'          => $distance->distance,
                    ];
            }

            $refAirports = DB::select("SELECT * FROM ref_airport WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_AIRPORT', 10000) . ";");
            foreach ($refAirports as $key => $refAirport) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refAirport->latitude;
                $lon2 = $refAirport->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_AIRPORT', 10000))
                    $data[] = [
                        'asset_id'          => $asset->id,
                        'ref_table_name'    => 'ref_airport',
                        'ref_id'            => $refAirport->id,
                        'distance'          => $distance->distance,
                    ];
            }

            $refMalls = DB::select("SELECT * FROM ref_mall WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_MALL', 5000) . ";");
            foreach ($refMalls as $key => $refMall) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refMall->latitude;
                $lon2 = $refMall->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_MALL', 5000))
                    $data[] = [
                        'asset_id'          => $asset->id,
                        'ref_table_name'    => 'ref_mall',
                        'ref_id'            => $refMall->id,
                        'distance'          => $distance->distance,
                    ];
            }

            $refHospitals = DB::select("SELECT * FROM ref_hospital WHERE ST_Distance(geography(ST_MakePoint(CAST(longitude AS double precision), CAST(latitude AS double precision))),geography(ST_MakePoint(" . $asset->longitude . "," . $asset->latitude . "))) <= " . env('DISTANCE_HOSPITAL', 5000) . ";");
            foreach ($refHospitals as $key => $refHospital) {
                $lat1 = $asset->latitude;
                $lon1 = $asset->longitude;
                $lat2 = $refHospital->latitude;
                $lon2 = $refHospital->longitude;

                $distance = DB::selectOne("SELECT ST_Distance(
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon1, $lat1), 4326), 26986),
                            ST_Transform(ST_SetSRID(ST_MakePoint($lon2, $lat2), 4326), 26986)
                            ) AS distance");

                if ($distance->distance <= env('DISTANCE_HOSPITAL', 5000))
                    $data[] = [
                        'asset_id'          => $asset->id,
                        'ref_table_name'    => 'ref_hospital',
                        'ref_id'            => $refHospital->id,
                        'distance'          => $distance->distance,
                    ];
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
                $data->whereRaw(
                    '(LOWER(ref_location.name_th) LIKE ? OR LOWER(ref_location.name_en) LIKE ?)',
                    ['%' . strtolower($request->search) . '%', '%' . strtolower($request->search) . '%']
                );
            }

            $data = $data->limit(100)->where('ref_location.is_active', true);

            return responsePaginate(Datatables::of($data)
                ->addColumn('ref_district', function ($item) {
                    return (object)[
                        "id"        => $item->ref_district_id,
                        "name_th"   => $item->ref_district_name_th,
                        "name_en"   => $item->ref_district_name_en,
                    ];
                })
                ->addColumn('ref_province', function ($item) {
                    return (object)[
                        "id"        => $item->ref_province_id,
                        "name_th"   => $item->ref_province_name_th,
                        "name_en"   => $item->ref_province_name_en,
                    ];
                })
                ->removeColumn(['ref_district_id', 'ref_district_name_th', 'ref_district_name_en', 'ref_province_id', 'ref_province_name_th', 'ref_province_name_en', 'is_active', 'created_by', 'updated_by', 'created_at', 'updated_at', 'deleted_at'])
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